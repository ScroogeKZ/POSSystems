// Material Design Toast Notifications System
class ToastNotifications {
    constructor() {
        this.container = this.createContainer();
        this.toasts = new Map();
        this.autoIncrement = 0;
    }

    createContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 8px;
            pointer-events: none;
        `;
        document.body.appendChild(container);
        return container;
    }

    show(message, type = 'info', duration = 4000, actions = []) {
        const toastId = ++this.autoIncrement;
        const toast = this.createToast(message, type, actions, toastId);
        
        this.container.appendChild(toast);
        this.toasts.set(toastId, toast);

        // Trigger entrance animation
        requestAnimationFrame(() => {
            toast.style.transform = 'translateY(0)';
            toast.style.opacity = '1';
        });

        // Auto dismiss
        if (duration > 0) {
            setTimeout(() => {
                this.dismiss(toastId);
            }, duration);
        }

        return toastId;
    }

    createToast(message, type, actions, toastId) {
        const toast = document.createElement('div');
        toast.className = `md-snackbar ${type}`;
        toast.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            transform: translateY(100%);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
            pointer-events: auto;
            box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.15);
            margin-bottom: 8px;
            max-width: 568px;
            min-width: 344px;
        `;

        const content = document.createElement('div');
        content.style.cssText = `
            flex: 1;
            display: flex;
            align-items: center;
            gap: 12px;
        `;

        // Add icon based on type
        const icon = this.getIcon(type);
        if (icon) {
            content.appendChild(icon);
        }

        const messageEl = document.createElement('span');
        messageEl.textContent = message;
        messageEl.style.cssText = `
            font-size: 14px;
            line-height: 1.5;
        `;
        content.appendChild(messageEl);

        toast.appendChild(content);

        // Add actions
        if (actions.length > 0) {
            const actionsContainer = document.createElement('div');
            actionsContainer.style.cssText = `
                display: flex;
                gap: 8px;
            `;

            actions.forEach(action => {
                const button = document.createElement('button');
                button.textContent = action.label;
                button.className = 'md-button-text';
                button.style.cssText = `
                    background: none;
                    border: none;
                    color: inherit;
                    font-weight: 500;
                    padding: 8px 12px;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: background-color 0.2s;
                `;
                
                button.addEventListener('click', () => {
                    if (action.handler) {
                        action.handler();
                    }
                    this.dismiss(toastId);
                });

                button.addEventListener('mouseenter', () => {
                    button.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                });

                button.addEventListener('mouseleave', () => {
                    button.style.backgroundColor = 'transparent';
                });

                actionsContainer.appendChild(button);
            });

            toast.appendChild(actionsContainer);
        }

        // Add close button for manual dismissal
        const closeButton = document.createElement('button');
        closeButton.innerHTML = '×';
        closeButton.style.cssText = `
            background: none;
            border: none;
            color: inherit;
            font-size: 18px;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-left: 8px;
        `;
        
        closeButton.addEventListener('click', () => {
            this.dismiss(toastId);
        });

        closeButton.addEventListener('mouseenter', () => {
            closeButton.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
        });

        closeButton.addEventListener('mouseleave', () => {
            closeButton.style.backgroundColor = 'transparent';
        });

        toast.appendChild(closeButton);

        return toast;
    }

    getIcon(type) {
        const iconMap = {
            success: '✓',
            error: '⚠',
            warning: '!',
            info: 'ℹ'
        };

        if (!iconMap[type]) return null;

        const icon = document.createElement('span');
        icon.textContent = iconMap[type];
        icon.style.cssText = `
            font-size: 18px;
            font-weight: bold;
            min-width: 20px;
            text-align: center;
        `;
        
        return icon;
    }

    dismiss(toastId) {
        const toast = this.toasts.get(toastId);
        if (!toast) return;

        toast.style.transform = 'translateY(-100%)';
        toast.style.opacity = '0';

        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            this.toasts.delete(toastId);
        }, 300);
    }

    dismissAll() {
        this.toasts.forEach((_, toastId) => {
            this.dismiss(toastId);
        });
    }

    // Convenience methods
    success(message, duration = 4000, actions = []) {
        return this.show(message, 'success', duration, actions);
    }

    error(message, duration = 6000, actions = []) {
        return this.show(message, 'error', duration, actions);
    }

    warning(message, duration = 5000, actions = []) {
        return this.show(message, 'warning', duration, actions);
    }

    info(message, duration = 4000, actions = []) {
        return this.show(message, 'info', duration, actions);
    }
}

// Initialize global toast notifications
window.Toast = new ToastNotifications();

// Replace standard alert, confirm with toast notifications
window.originalAlert = window.alert;
window.originalConfirm = window.confirm;

window.alert = function(message) {
    window.Toast.info(message);
};

window.confirm = function(message) {
    return new Promise((resolve) => {
        window.Toast.warning(message, 0, [
            {
                label: 'Жоқ / Нет',
                handler: () => resolve(false)
            },
            {
                label: 'Иә / Да',
                handler: () => resolve(true)
            }
        ]);
    });
};

// Show flash messages as toasts
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        const type = message.classList.contains('alert-success') ? 'success' :
                    message.classList.contains('alert-danger') ? 'error' :
                    message.classList.contains('alert-warning') ? 'warning' : 'info';
        
        window.Toast.show(message.textContent.trim(), type);
        message.style.display = 'none';
    });
});

// Expose toast for AJAX responses
window.showToast = function(message, type = 'info', duration = 4000) {
    return window.Toast.show(message, type, duration);
};

// Mobile optimizations
if (window.innerWidth <= 768) {
    const style = document.createElement('style');
    style.textContent = `
        #toast-container {
            left: 16px !important;
            right: 16px !important;
            transform: none !important;
            max-width: none !important;
        }
        
        .md-snackbar {
            min-width: auto !important;
            max-width: none !important;
            margin: 0 !important;
        }
    `;
    document.head.appendChild(style);
}