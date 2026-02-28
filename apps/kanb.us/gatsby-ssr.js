const React = require("react");

exports.onRenderBody = ({ setHeadComponents }) => {
  setHeadComponents([
    <script
      key="system-theme-sync"
      dangerouslySetInnerHTML={{
        __html: `
          (function() {
            try {
              localStorage.removeItem('theme');
              var isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
              var root = document.documentElement;
              if (isDark) {
                root.classList.add('dark');
                root.classList.remove('light');
              } else {
                root.classList.add('light');
                root.classList.remove('dark');
              }
            } catch (e) {}
          })();
        `,
      }}
    />,
  ]);
};
