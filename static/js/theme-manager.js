// Theme Management с полной интеграцией
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.init();
    }

    init() {
        // Применяем тему до загрузки DOM
        this.applyTheme(this.currentTheme, false);
        
        // Инициализация после загрузки DOM
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeUI();
        });
    }

    applyTheme(theme, animate = true) {
        const html = document.documentElement;
        const themeColor = document.querySelector('meta[name="theme-color"]');
        
        if (animate) {
            html.style.transition = 'background-color 0.3s ease, color 0.3s ease';
        }
        
        html.setAttribute('data-theme', theme);
        
        // Обновляем цвет браузера
        if (themeColor) {
            themeColor.setAttribute('content', theme === 'dark' ? '#1a1a1a' : '#007bff');
        }
        
        // Сохраняем в localStorage
        localStorage.setItem('theme', theme);
        this.currentTheme = theme;
        
        // Обновляем иконку
        this.updateThemeIcon();
        
        if (animate) {
            setTimeout(() => {
                html.style.transition = '';
            }, 300);
        }
    }

    toggleTheme() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme(newTheme);
        
        // Показываем уведомление
        if (window.Toast) {
            window.Toast.success(`Тема изменена на ${newTheme === 'dark' ? 'темную' : 'светлую'}`);
        }
    }

    updateThemeIcon() {
        const themeIcon = document.getElementById('themeIcon');
        if (themeIcon) {
            themeIcon.className = this.currentTheme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
        }
    }

    initializeUI() {
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle && !themeToggle.hasAttribute('data-theme-bound')) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
            themeToggle.setAttribute('data-theme-bound', 'true');
        }
        
        // Горячие клавиши
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 't') {
                e.preventDefault();
                this.toggleTheme();
            }
            if (e.key === 'F12') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
        
        // Обновляем иконку при инициализации
        this.updateThemeIcon();
    }

    getCurrentTheme() {
        return this.currentTheme;
    }
}

// Инициализация темы ДО загрузки DOM для предотвращения мерцания
const initThemeEarly = () => {
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) {
        themeColor.setAttribute('content', savedTheme === 'dark' ? '#1a1a1a' : '#007bff');
    }
};

// Выполняем немедленно
initThemeEarly();

// Создаем глобальный экземпляр
window.themeManager = new ThemeManager();