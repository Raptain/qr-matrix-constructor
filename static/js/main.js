const themeToggle = document.getElementById('theme-toggle');
if(themeToggle) {
    themeToggle.addEventListener('click', () => {
        const html = document.documentElement;
        const current = html.getAttribute('data-bs-theme');
        const newTheme = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    });
    const saved = localStorage.getItem('theme');
    if(saved) document.documentElement.setAttribute('data-bs-theme', saved);
}