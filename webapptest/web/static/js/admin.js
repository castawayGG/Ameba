/**
 * ADMIN PANEL SPA LOGIC
 * - Hash-based routing
 * - Mock data rendering
 * - UI event handling (modals, forms, etc.)
 */
document.addEventListener('DOMContentLoaded', () => {
    
    // --- STATE & MOCK DATA ---
    const MOCK_ACCOUNTS = Array.from({ length: 53 }, (_, i) => ({
        id: i + 1,
        phone: `+7926${String(Math.floor(Math.random() * 9000000) + 1000000)}`,
        username: `user_${Math.random().toString(36).substring(7)}`,
        status: ['active', 'banned', 'checking'][Math.floor(Math.random() * 3)],
        last_activity: new Date(Date.now() - Math.random() * 1e10).toISOString().split('T')[0],
    }));

    const MOCK_PROXIES = [
        { ip: '192.168.1.1', port: 8080, type: 'HTTP', status: 'working', speed: 120, last_check: '2024-05-20 10:00' },
        { ip: '10.0.0.5', port: 3128, type: 'SOCKS5', status: 'dead', speed: null, last_check: '2024-05-20 09:45' },
        { ip: '172.16.0.10', port: 1080, type: 'SOCKS5', status: 'working', speed: 85, last_check: '2024-05-20 10:02' },
        { ip: '203.0.113.25', port: 8000, type: 'HTTP', status: 'checking', speed: null, last_check: '2024-05-19 18:00' },
    ];
    
    // --- UI ELEMENTS ---
    const navItems = document.querySelectorAll('.nav-item');
    const contentSections = document.querySelectorAll('.content-section');
    const pageTitle = document.getElementById('page-title');
    const accountsTableBody = document.getElementById('accounts-table-body');
    const proxiesTableBody = document.getElementById('proxies-table-body');
    const accountsPagination = document.getElementById('accounts-pagination');
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');

    // --- ROUTING ---
    const handleRouteChange = () => {
        const hash = window.location.hash || '#dashboard';
        const sectionId = hash.substring(1);

        contentSections.forEach(section => section.classList.remove('active'));
        const activeSection = document.getElementById(sectionId);
        if (activeSection) activeSection.classList.add('active');

        navItems.forEach(item => item.classList.remove('active'));
        const activeLink = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
            pageTitle.textContent = activeLink.querySelector('span').textContent;
        }
    };
    
    // --- RENDERING FUNCTIONS ---
    const renderAccounts = (page = 1, perPage = 10, data = MOCK_ACCOUNTS) => {
        accountsTableBody.innerHTML = '';
        const start = (page - 1) * perPage;
        const end = start + perPage;
        const paginatedData = data.slice(start, end);

        if (paginatedData.length === 0) {
            accountsTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem;">Нет данных для отображения</td></tr>';
            renderPagination(0, page, perPage);
            return;
        }

        paginatedData.forEach(acc => {
            const statusTag = acc.status === 'active' ? 'tag-success' : acc.status === 'banned' ? 'tag-danger' : 'tag-warning';
            const row = `
                <tr>
                    <td><input type="checkbox" class="select-account" data-id="${acc.id}"></td>
                    <td>${acc.phone}</td>
                    <td>@${acc.username}</td>
                    <td><span class="tag ${statusTag}">${acc.status}</span></td>
                    <td>${acc.last_activity}</td>
                    <td class="table-actions">
                        <a href="#" class="edit-account" data-id="${acc.id}">Изменить</a>
                        <a href="#" class="delete-account delete" data-id="${acc.id}">Удалить</a>
                    </td>
                </tr>
            `;
            accountsTableBody.insertAdjacentHTML('beforeend', row);
        });
        
        renderPagination(data.length, page, perPage);
    };

    const renderProxies = () => {
        proxiesTableBody.innerHTML = '';
        MOCK_PROXIES.forEach(proxy => {
            const statusTag = proxy.status === 'working' ? 'tag-success' : proxy.status === 'dead' ? 'tag-danger' : 'tag-warning';
            const row = `
                <tr>
                    <td>${proxy.ip}:${proxy.port}</td>
                    <td>${proxy.type}</td>
                    <td><span class="tag ${statusTag}">${proxy.status}</span></td>
                    <td>${proxy.speed ? `${proxy.speed} ms` : 'N/A'}</td>
                    <td>${proxy.last_check}</td>
                    <td class="table-actions">
                        <a href="#" class="test-proxy" data-ip="${proxy.ip}">Тест</a>
                        <a href="#" class="delete-proxy delete" data-ip="${proxy.ip}">Удалить</a>
                    </td>
                </tr>
            `;
            proxiesTableBody.insertAdjacentHTML('beforeend', row);
        });
    };

    const renderPagination = (totalItems, currentPage, perPage) => {
        accountsPagination.innerHTML = '';
        const totalPages = Math.ceil(totalItems / perPage);
        if (totalPages <= 1) return;

        for (let i = 1; i <= totalPages; i++) {
            const link = document.createElement('a');
            link.href = '#';
            link.className = 'page-link';
            if (i === currentPage) link.classList.add('active');
            link.textContent = i;
            link.dataset.page = i;
            accountsPagination.appendChild(link);
        }
    };
    
    // --- UI HELPERS ---
    const showToast = (message, type = 'info') => {
        toastMessage.textContent = message;
        toast.className = `toast show ${type}`;
        setTimeout(() => toast.classList.remove('show'), 3000);
    };
    
    const confirmAction = (title, text) => {
        return new Promise((resolve) => {
            const modal = document.getElementById('confirm-modal');
            modal.querySelector('#confirm-title').textContent = title;
            modal.querySelector('#confirm-text').textContent = text;
            modal.style.display = 'flex';
            
            const close = () => modal.style.display = 'none';

            document.getElementById('confirm-ok').onclick = () => { close(); resolve(true); };
            document.getElementById('confirm-cancel').onclick = () => { close(); resolve(false); };
            modal.querySelector('.modal-close').onclick = () => { close(); resolve(false); };
        });
    };
    
    // --- MODAL HANDLING ---
    document.querySelectorAll('[data-modal]').forEach(button => {
        button.addEventListener('click', () => {
            const modal = document.getElementById(button.dataset.modal);
            if (modal) modal.style.display = 'flex';
        });
    });

    document.querySelectorAll('.modal-close, .modal').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target === el) {
                el.closest('.modal').style.display = 'none';
            }
        });
    });
    
    // --- EVENT LISTENERS ---
    window.addEventListener('hashchange', handleRouteChange);
    window.addEventListener('load', handleRouteChange);

    document.getElementById('accounts-search').addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filteredData = MOCK_ACCOUNTS.filter(acc => 
            acc.phone.includes(query) || acc.username.toLowerCase().includes(query)
        );
        renderAccounts(1, 10, filteredData);
    });
    
    accountsPagination.addEventListener('click', (e) => {
        if (e.target.matches('.page-link')) {
            e.preventDefault();
            const page = parseInt(e.target.dataset.page, 10);
            renderAccounts(page);
        }
    });
    
    accountsTableBody.addEventListener('click', async (e) => {
        if (e.target.matches('.delete-account')) {
            e.preventDefault();
            const confirmed = await confirmAction('Удалить аккаунт?', 'Это действие нельзя будет отменить.');
            if (confirmed) {
                showToast('Аккаунт успешно удален.', 'success');
                // Here you would call API to delete and then re-render
            }
        }
    });

    document.getElementById('add-proxy-form').addEventListener('submit', e => {
        e.preventDefault();
        const list = document.getElementById('proxy-list').value;
        if(list.trim()){
            showToast(`${list.split('\n').length} прокси добавлено.`, 'success');
            document.getElementById('add-proxy-modal').style.display = 'none';
            e.target.reset();
        }
    });
    
    // --- INITIAL RENDER ---
    renderAccounts();
    renderProxies();
});