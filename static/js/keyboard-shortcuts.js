// Keyboard Shortcuts для POS системы
class POSKeyboardShortcuts {
    constructor() {
        this.shortcuts = new Map();
        this.isEnabled = true;
        this.currentPage = this.detectCurrentPage();
        this.init();
    }

    detectCurrentPage() {
        const path = window.location.pathname;
        if (path.includes('/pos')) return 'pos';
        if (path.includes('/inventory')) return 'inventory';
        if (path.includes('/reports')) return 'reports';
        if (path.includes('/auth')) return 'auth';
        return 'dashboard';
    }

    init() {
        this.registerShortcuts();
        this.bindEvents();
        this.createHelpModal();
        this.showInitialHint();
    }

    registerShortcuts() {
        // Глобальные горячие клавиши
        this.addShortcut('F1', 'Помощь / Справка', () => this.showHelp());
        this.addShortcut('F2', 'POS Терминал', () => this.navigateTo('/pos'));
        this.addShortcut('F3', 'Инвентарь', () => this.navigateTo('/inventory'));
        this.addShortcut('F4', 'Отчеты', () => this.navigateTo('/reports'));
        this.addShortcut('F5', 'Обновить страницу', () => window.location.reload());
        this.addShortcut('F11', 'Полноэкранный режим', () => this.toggleFullscreen());
        this.addShortcut('F12', 'Переключить тему', () => this.toggleTheme());

        // Горячие клавиши для POS терминала
        if (this.currentPage === 'pos') {
            this.addShortcut('Ctrl+N', 'Новая транзакция', () => this.startNewTransaction());
            this.addShortcut('Ctrl+S', 'Сохранить транзакцию', () => this.saveTransaction());
            this.addShortcut('Ctrl+P', 'Оплата наличными', () => this.payWithCash());
            this.addShortcut('Ctrl+C', 'Оплата картой', () => this.payWithCard());
            this.addShortcut('Ctrl+D', 'Приостановить транзакцию', () => this.suspendTransaction());
            this.addShortcut('Ctrl+R', 'Восстановить транзакцию', () => this.restoreTransaction());
            this.addShortcut('Ctrl+F', 'Поиск товара', () => this.focusSearch());
            this.addShortcut('Ctrl+B', 'Сканировать штрих-код', () => this.openBarcodeScanner());
            this.addShortcut('Escape', 'Отмена / Очистить', () => this.cancelAction());
            this.addShortcut('Enter', 'Подтвердить', () => this.confirmAction());
        }

        // Горячие клавиши для инвентаря
        if (this.currentPage === 'inventory') {
            this.addShortcut('Ctrl+N', 'Добавить товар', () => this.addProduct());
            this.addShortcut('Ctrl+F', 'Поиск товаров', () => this.focusSearch());
            this.addShortcut('Ctrl+E', 'Экспорт данных', () => this.exportData());
        }

        // Горячие клавиши для отчетов
        if (this.currentPage === 'reports') {
            this.addShortcut('Ctrl+E', 'Экспорт отчета', () => this.exportReport());
            this.addShortcut('Ctrl+P', 'Печать отчета', () => this.printReport());
            this.addShortcut('Ctrl+R', 'Обновить данные', () => this.refreshReports());
        }

        // Навигационные клавиши
        this.addShortcut('Alt+H', 'Главная', () => this.navigateTo('/'));
        this.addShortcut('Alt+L', 'Выйти', () => this.logout());
    }

    addShortcut(key, description, handler) {
        this.shortcuts.set(key.toLowerCase(), {
            key,
            description,
            handler,
            page: this.currentPage
        });
    }

    bindEvents() {
        document.addEventListener('keydown', (e) => {
            if (!this.isEnabled) return;
            
            // Игнорировать если фокус на поле ввода (кроме некоторых клавиш)
            if (this.isInputFocused() && !this.isGlobalShortcut(e)) return;

            const key = this.getKeyString(e);
            const shortcut = this.shortcuts.get(key.toLowerCase());

            if (shortcut) {
                e.preventDefault();
                e.stopPropagation();
                
                try {
                    shortcut.handler();
                    this.showShortcutFeedback(shortcut.key, shortcut.description);
                } catch (error) {
                    console.error('Shortcut execution error:', error);
                    window.Toast?.error('Ошибка выполнения горячей клавиши');
                }
            }
        });

        // Показать подсказку при удержании Alt
        let altHintTimeout;
        document.addEventListener('keydown', (e) => {
            if (e.altKey && !e.ctrlKey && !e.shiftKey) {
                clearTimeout(altHintTimeout);
                altHintTimeout = setTimeout(() => {
                    this.showQuickHint();
                }, 1000);
            }
        });

        document.addEventListener('keyup', (e) => {
            if (!e.altKey) {
                clearTimeout(altHintTimeout);
                this.hideQuickHint();
            }
        });
    }

    getKeyString(e) {
        const parts = [];
        
        if (e.ctrlKey) parts.push('Ctrl');
        if (e.altKey) parts.push('Alt');
        if (e.shiftKey) parts.push('Shift');
        
        let key = e.key;
        
        // Функциональные клавиши
        if (key.startsWith('F') && key.length <= 3) {
            parts.push(key);
        } else if (key === 'Escape') {
            parts.push('Escape');
        } else if (key === 'Enter') {
            parts.push('Enter');
        } else if (key.length === 1) {
            parts.push(key.toUpperCase());
        }
        
        return parts.join('+');
    }

    isInputFocused() {
        const activeElement = document.activeElement;
        return activeElement && (
            activeElement.tagName === 'INPUT' ||
            activeElement.tagName === 'TEXTAREA' ||
            activeElement.tagName === 'SELECT' ||
            activeElement.contentEditable === 'true'
        );
    }

    isGlobalShortcut(e) {
        const key = this.getKeyString(e);
        const globalKeys = ['F1', 'F2', 'F3', 'F4', 'F5', 'F11', 'F12', 'Alt+H', 'Alt+L'];
        return globalKeys.includes(key);
    }

    // Действия горячих клавиш
    navigateTo(path) {
        window.location.href = path;
    }

    showHelp() {
        document.getElementById('shortcutsModal')?.click() || this.createAndShowHelp();
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                window.Toast?.warning('Не удалось войти в полноэкранный режим');
            });
        } else {
            document.exitFullscreen();
        }
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        window.Toast?.success(`Тема изменена на ${newTheme === 'dark' ? 'темную' : 'светлую'}`);
    }

    focusSearch() {
        const searchInput = document.querySelector('#productSearch, #searchInput, .search-input, input[type="search"]');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    // POS специфичные действия
    startNewTransaction() {
        const startBtn = document.querySelector('#startTransactionBtn, .btn-start');
        if (startBtn) startBtn.click();
    }

    saveTransaction() {
        const saveBtn = document.querySelector('#saveTransactionBtn, .btn-save');
        if (saveBtn) saveBtn.click();
    }

    payWithCash() {
        const cashBtn = document.querySelector('#cashPaymentBtn, .btn-cash');
        if (cashBtn) cashBtn.click();
    }

    payWithCard() {
        const cardBtn = document.querySelector('#cardPaymentBtn, .btn-card');
        if (cardBtn) cardBtn.click();
    }

    suspendTransaction() {
        const suspendBtn = document.querySelector('#suspendBtn, .btn-suspend');
        if (suspendBtn) suspendBtn.click();
    }

    restoreTransaction() {
        const restoreBtn = document.querySelector('#restoreBtn, .btn-restore');
        if (restoreBtn) restoreBtn.click();
    }

    openBarcodeScanner() {
        const scannerBtn = document.querySelector('#barcodeScannerBtn, .btn-scanner');
        if (scannerBtn) scannerBtn.click();
    }

    cancelAction() {
        const cancelBtn = document.querySelector('#cancelBtn, .btn-cancel');
        if (cancelBtn) {
            cancelBtn.click();
        } else {
            // Закрыть модальные окна
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(modal => {
                const closeBtn = modal.querySelector('.btn-close, .close');
                if (closeBtn) closeBtn.click();
            });
        }
    }

    confirmAction() {
        const confirmBtn = document.querySelector('#confirmBtn, .btn-confirm, .btn-primary:focus');
        if (confirmBtn) confirmBtn.click();
    }

    addProduct() {
        const addBtn = document.querySelector('#addProductBtn, .btn-add-product');
        if (addBtn) addBtn.click();
    }

    exportData() {
        const exportBtn = document.querySelector('#exportBtn, .btn-export');
        if (exportBtn) exportBtn.click();
    }

    exportReport() {
        const exportBtn = document.querySelector('#exportReportBtn, .btn-export-report');
        if (exportBtn) exportBtn.click();
    }

    printReport() {
        window.print();
    }

    refreshReports() {
        const refreshBtn = document.querySelector('#refreshBtn, .btn-refresh');
        if (refreshBtn) {
            refreshBtn.click();
        } else {
            window.location.reload();
        }
    }

    logout() {
        if (confirm('Вы уверены, что хотите выйти?')) {
            window.location.href = '/auth/logout';
        }
    }

    // UI методы
    showShortcutFeedback(key, description) {
        const feedback = document.createElement('div');
        feedback.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--md-surface-container);
            color: var(--md-on-surface);
            padding: 8px 16px;
            border-radius: 8px;
            box-shadow: var(--md-elevation-3);
            font-size: 12px;
            z-index: 10000;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.2s ease;
        `;
        
        feedback.innerHTML = `<strong>${key}</strong>: ${description}`;
        document.body.appendChild(feedback);

        requestAnimationFrame(() => {
            feedback.style.opacity = '1';
            feedback.style.transform = 'translateX(0)';
        });

        setTimeout(() => {
            feedback.style.opacity = '0';
            feedback.style.transform = 'translateX(100%)';
            setTimeout(() => feedback.remove(), 200);
        }, 2000);
    }

    showInitialHint() {
        if (!localStorage.getItem('shortcutsHintShown')) {
            setTimeout(() => {
                window.Toast?.info('Нажмите F1 для просмотра горячих клавиш', 5000);
                localStorage.setItem('shortcutsHintShown', 'true');
            }, 2000);
        }
    }

    showQuickHint() {
        if (document.getElementById('quickHint')) return;

        const hint = document.createElement('div');
        hint.id = 'quickHint';
        hint.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--md-surface-container);
            color: var(--md-on-surface);
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: var(--md-elevation-3);
            font-size: 12px;
            z-index: 10000;
            max-width: 300px;
            opacity: 0;
            transition: opacity 0.2s ease;
        `;

        const shortcuts = Array.from(this.shortcuts.values())
            .filter(s => s.page === this.currentPage || s.key.startsWith('F'))
            .slice(0, 5);

        hint.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 8px;">Горячие клавиши:</div>
            ${shortcuts.map(s => `<div><kbd>${s.key}</kbd> ${s.description}</div>`).join('')}
            <div style="margin-top: 8px; font-style: italic;">F1 - все горячие клавиши</div>
        `;

        document.body.appendChild(hint);
        requestAnimationFrame(() => hint.style.opacity = '1');
    }

    hideQuickHint() {
        const hint = document.getElementById('quickHint');
        if (hint) {
            hint.style.opacity = '0';
            setTimeout(() => hint.remove(), 200);
        }
    }

    createHelpModal() {
        if (document.getElementById('shortcutsModal')) return;

        const modal = document.createElement('div');
        modal.innerHTML = `
            <div class="modal fade" id="shortcutsModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content md-dialog">
                        <div class="modal-header">
                            <h5 class="modal-title md-dialog-header">Горячие клавиши POS системы</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body md-dialog-content" id="shortcutsContent">
                            <!-- Контент будет добавлен динамически -->
                        </div>
                        <div class="modal-footer md-dialog-actions">
                            <button type="button" class="btn btn-secondary md-button-outlined" data-bs-dismiss="modal">Закрыть</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        this.updateHelpContent();
    }

    updateHelpContent() {
        const content = document.getElementById('shortcutsContent');
        if (!content) return;

        const groupedShortcuts = {};
        this.shortcuts.forEach(shortcut => {
            const page = shortcut.page || 'global';
            if (!groupedShortcuts[page]) groupedShortcuts[page] = [];
            groupedShortcuts[page].push(shortcut);
        });

        const pageNames = {
            global: 'Глобальные',
            pos: 'POS Терминал',
            inventory: 'Инвентарь',
            reports: 'Отчеты',
            dashboard: 'Панель управления'
        };

        let html = '';
        Object.keys(groupedShortcuts).forEach(page => {
            html += `
                <div class="mb-4">
                    <h6 class="text-primary">${pageNames[page] || page}</h6>
                    <div class="row">
                        ${groupedShortcuts[page].map(s => `
                            <div class="col-md-6 mb-2">
                                <div class="d-flex justify-content-between">
                                    <kbd class="me-2">${s.key}</kbd>
                                    <span class="text-muted">${s.description}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });

        content.innerHTML = html;
    }

    createAndShowHelp() {
        this.createHelpModal();
        const modal = new bootstrap.Modal(document.getElementById('shortcutsModal'));
        modal.show();
    }

    enable() {
        this.isEnabled = true;
    }

    disable() {
        this.isEnabled = false;
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.POSShortcuts = new POSKeyboardShortcuts();
});

// Добавление стилей для kbd элементов
document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = `
        kbd {
            background-color: var(--md-surface-container-high);
            color: var(--md-on-surface);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.875em;
            font-weight: 600;
            border: 1px solid var(--md-outline-variant);
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
    `;
    document.head.appendChild(style);
});