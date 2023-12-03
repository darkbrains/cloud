document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const themeToggleIcon = document.getElementById('theme-toggle-icon');

    const currentTheme = localStorage.getItem('theme');
    if (currentTheme === 'dark') {
        document.body.classList.add('dark-mode');
        themeToggleIcon.textContent = '☀️';
        themeToggleIcon.classList.remove('moon');
        themeToggleIcon.classList.add('sun');
    }

    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        let theme = 'light';
        if (document.body.classList.contains('dark-mode')) {
            theme = 'dark';
            themeToggleIcon.textContent = '☀️';
            themeToggleIcon.classList.remove('moon');
            themeToggleIcon.classList.add('sun');
        } else {
            themeToggleIcon.textContent = '☽';
            themeToggleIcon.classList.remove('sun');
            themeToggleIcon.classList.add('moon');
        }
        localStorage.setItem('theme', theme);
    });
});
