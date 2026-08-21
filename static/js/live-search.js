(() => {
  function initializeLiveSearch(form) {
    if (form.dataset.liveSearchReady === 'true') return;
    form.dataset.liveSearchReady = 'true';

    const targetSelector = form.dataset.liveSearchTarget;
    const target = document.querySelector(targetSelector);
    const searchInput = form.querySelector('input[name="q"]');
    if (!target || !searchInput) return;

    let debounceTimer = null;
    let activeRequest = null;

    async function updateResults() {
      if (activeRequest) activeRequest.abort();
      activeRequest = new AbortController();
      const params = new URLSearchParams(new FormData(form));
      params.delete('page');
      const url = `${form.action || window.location.pathname}?${params.toString()}`;

      target.setAttribute('aria-busy', 'true');
      target.classList.add('opacity-60');
      try {
        const response = await fetch(url, {
          headers: {'X-Requested-With': 'XMLHttpRequest'},
          signal: activeRequest.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
        const newTarget = parsed.querySelector(targetSelector);
        if (!newTarget) throw new Error('No se encontró el resultado de búsqueda.');
        target.innerHTML = newTarget.innerHTML;
        document.querySelectorAll('[data-live-search-sync]').forEach(element => {
          const key = element.dataset.liveSearchSync;
          const replacement = parsed.querySelector(`[data-live-search-sync="${key}"]`);
          if (replacement) element.innerHTML = replacement.innerHTML;
        });
        window.history.replaceState({}, '', url);
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('No se pudo actualizar la búsqueda:', error);
        }
      } finally {
        target.removeAttribute('aria-busy');
        target.classList.remove('opacity-60');
      }
    }

    searchInput.addEventListener('input', () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(updateResults, 300);
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      window.clearTimeout(debounceTimer);
      updateResults();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-live-search-target]').forEach(initializeLiveSearch);
  });
})();
