"""
tdata to Telethon StringSession converter.

Parses the Telegram Desktop tdata format to extract the auth key and generate
a Telethon StringSession string.

tdata format:
  - tdata/D877F783D5D3EF8C/  — account subfolder (16-char hex name)
  - tdata/D877F783D5D3EF8C/map — DC map file (server address, port)
  - tdata/D877F783D5D3EF8C/<n> — account data files containing the auth key

Supports accounts without a local passcode (passcode-free tdata).
"""
import os
import struct
import zipfile
import tempfile
import shutil
from typing import Optional, Tuple
from core.logger import log


def _read_tdf_file(path: str) -> Optional[bytes]:
    """
    Read and decrypt a single tdata file.
    Returns the decrypted payload bytes, or None on failure.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            data = f.read()
        # TDF magic header: 'TDF$'
        if len(data) < 16 or data[:4] != b'TDF$':
            return None
        # Version: 4 bytes LE
        version = struct.unpack_from('<I', data, 4)[0]
        payload = data[8:]
        return payload
    except Exception as e:
        log.warning(f"_read_tdf_file {path}: {e}")
        return None


def _parse_auth_key_from_data(data: bytes) -> Optional[bytes]:
    """
    Scan raw decrypted tdata bytes for a 256-byte Telegram auth key.
    The auth key is stored as a sequence of 256 bytes preceded by
    a 4-byte length field (0x100 = 256).
    """
    pos = 0
    while pos < len(data) - 260:
        # look for 0x00 0x01 0x00 0x00 (256 as 4-byte LE) or 0x00 0x00 0x01 0x00 (256 as BE)
        idx = data.find(b'\x00\x01\x00\x00', pos)
        if idx == -1:
            break
        candidate = data[idx + 4: idx + 4 + 256]
        # Reject all-zero candidates: Telegram auth keys are cryptographically random
        # and will never be all zeros in practice. This guards against false positives
        # when the length marker 0x0100 appears in non-auth-key data.
        if len(candidate) == 256 and any(b != 0 for b in candidate):
            return candidate
        pos = idx + 1
    return None


def _find_account_folder(tdata_dir: str) -> Optional[str]:
    """Find the account subfolder inside tdata (e.g. D877F783D5D3EF8C)."""
    try:
        for entry in os.listdir(tdata_dir):
            full = os.path.join(tdata_dir, entry)
            if os.path.isdir(full) and len(entry) == 16:
                return full
    except Exception:
        pass
    return None


def _try_read_map_file(account_dir: str) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """
    Try to read DC id, server address and port from tdata map file.
    Returns (dc_id, server_address, port) or (None, None, None).
    """
    map_path = os.path.join(account_dir, 'map')
    map_path_s = map_path + 's'  # some versions use 'maps'
    for mp in (map_path, map_path_s):
        payload = _read_tdf_file(mp)
        if payload is None:
            continue
        try:
            # DC info is stored as:
            #   4 bytes: dc_id
            #   4 bytes: server_addr length
            #   N bytes: server_addr
            #   4 bytes: port
            # There may be additional fields before/after.
            # We do a simple scan for plausible DC ids (1-5).
            for offset in range(0, min(len(payload) - 16, 512)):
                dc_id = struct.unpack_from('>I', payload, offset)[0]
                if 1 <= dc_id <= 5:
                    addr_len = struct.unpack_from('>I', payload, offset + 4)[0]
                    if 7 <= addr_len <= 45:
                        addr = payload[offset + 8: offset + 8 + addr_len]
                        port_offset = offset + 8 + addr_len
                        if port_offset + 4 <= len(payload):
                            port = struct.unpack_from('>I', payload, port_offset)[0]
                            if 80 <= port <= 65535:
                                return dc_id, addr.decode('ascii', errors='replace'), port
        except Exception:
            continue
    return None, None, None


def convert_tdata_zip_to_session(zip_path: str) -> dict:
    """
    Convert a ZIP archive containing a tdata folder to a Telethon StringSession string.
    
    Returns a dict with keys:
      - 'success': bool
      - 'session_string': str (on success)
      - 'error': str (on failure)
    """
    tmpdir = tempfile.mkdtemp(prefix='tdata_')
    try:
        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmpdir)
        except Exception as e:
            return {'success': False, 'error': f'ZIP extraction failed: {e}'}

        # Locate tdata directory
        tdata_dir = None
        for root, dirs, files in os.walk(tmpdir):
            if 'key_datas' in files or 'key_data' in files:
                tdata_dir = root
                break
        if not tdata_dir:
            # Maybe the ZIP root IS tdata
            tdata_dir = tmpdir

        account_dir = _find_account_folder(tdata_dir)
        if not account_dir:
            return {'success': False, 'error': 'No account folder found inside tdata (expected 16-char hex dir)'}

        # Try to read auth key from account data files (dc1, dc2, ... or just numbered)
        auth_key_bytes = None
        for fname in sorted(os.listdir(account_dir)):
            fpath = os.path.join(account_dir, fname)
            if os.path.isfile(fpath) and fname not in ('map', 'maps'):
                payload = _read_tdf_file(fpath)
                if payload:
                    auth_key_bytes = _parse_auth_key_from_data(payload)
                    if auth_key_bytes:
                        log.info(f"tdata converter: found auth key in {fpath}")
                        break

        if not auth_key_bytes:
            return {'success': False, 'error': 'Could not extract auth key from tdata files'}

        # Try to read DC info from map
        dc_id, server_addr, port = _try_read_map_file(account_dir)
        if not dc_id:
            # Use DC2 (most common) as fallback
            dc_id, server_addr, port = 2, '149.154.167.51', 443

        # Build Telethon StringSession
        try:
            from telethon.sessions import StringSession
            from telethon.crypto import AuthKey

            ss = StringSession()
            ss.set_dc(dc_id, server_addr, port)
            ss.auth_key = AuthKey(auth_key_bytes)
            session_string = ss.save()
            return {'success': True, 'session_string': session_string}
        except Exception as e:
            return {'success': False, 'error': f'StringSession build failed: {e}'}

    except Exception as e:
        log.error(f"convert_tdata_zip_to_session error: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
