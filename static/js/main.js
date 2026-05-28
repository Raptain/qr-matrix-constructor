// Переключение темы (светлая/тёмная)
const themeToggle = document.getElementById('theme-toggle');
if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const html = document.documentElement;
        const current = html.getAttribute('data-bs-theme');
        const newTheme = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        // Обновляем текст кнопки
        themeToggle.textContent = newTheme === 'dark' ? 'Светлая' : 'Тёмная';
    });
    
    // Загружаем сохранённую тему
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        themeToggle.textContent = savedTheme === 'dark' ? 'Светлая' : 'Тёмная';
    } else {
        themeToggle.textContent = 'Тёмная';
    }
}