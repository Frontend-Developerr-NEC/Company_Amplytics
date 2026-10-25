(() => {
  const themeToggle = document.querySelector("[data-theme-toggle]");
  if (!themeToggle) return;

  function setTheme(theme, persist = true) {
    if (theme !== "black" && theme !== "white") return;
    document.documentElement.dataset.theme = theme;
    const isBlackTheme = theme === "black";
    themeToggle.value = isBlackTheme ? "1" : "0";
    themeToggle.setAttribute("aria-valuetext", `${isBlackTheme ? "Black" : "White"} theme`);
    themeToggle.setAttribute("title", `${isBlackTheme ? "Black" : "White"} theme`);

    if (persist) {
      try {
        localStorage.setItem("amplytics-theme", theme);
      } catch (error) {
        console.warn("Unable to save the theme preference.", error);
      }
    }

    document.dispatchEvent(new CustomEvent("amplytics-theme-change", { detail: { theme } }));
  }

  themeToggle.addEventListener("input", () => {
    setTheme(themeToggle.value === "1" ? "black" : "white");
  });
  setTheme(document.documentElement.dataset.theme, false);

  window.addEventListener("storage", (event) => {
    if (event.key === "amplytics-theme" && (event.newValue === "black" || event.newValue === "white")) {
      setTheme(event.newValue, false);
    }
  });
})();
