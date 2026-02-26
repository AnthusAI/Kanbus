const React = require("react");

exports.onRenderBody = ({ setHeadComponents }) => {
  setHeadComponents([
    <script
      key="dark-mode-script"
      dangerouslySetInnerHTML={{
        __html: `
          (function() {
            function setTheme(theme) {
              if (theme === 'dark') {
                document.documentElement.classList.add('dark');
                document.documentElement.classList.remove('light');
              } else {
                document.documentElement.classList.add('light');
                document.documentElement.classList.remove('dark');
              }
            }
            
            var preferredTheme;
            try {
              preferredTheme = localStorage.getItem('theme');
            } catch (err) { }
            
            var darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
            
            setTheme(preferredTheme || (darkQuery.matches ? 'dark' : 'light'));
            
            darkQuery.addEventListener('change', function(e) {
              if (!preferredTheme) {
                setTheme(e.matches ? 'dark' : 'light');
              }
            });
          })();
        `,
      }}
    />,
  ]);
};
