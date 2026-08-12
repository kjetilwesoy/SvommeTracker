/* auto-data-label.js
   Adds data-label attributes by reading the table headers and wraps cell content with a .value span.
   Runs once on DOMContentLoaded for tables with class="responsive".
   Exposes window.svtInjectLabels(table) so your existing code can call it after updating tbody.innerHTML.
*/
(function () {
  function injectForTable(table) {
    if (!table) return;
    const thead = table.querySelector('thead');
    const headers = thead ? Array.from(thead.querySelectorAll('th')).map(th => th.textContent.trim()) : [];

    table.querySelectorAll('tbody tr').forEach(function (tr) {
      // Skip rows that are just detail containers without regular td cells
      Array.from(tr.children).forEach(function (td, i) {
        if (td.tagName.toLowerCase() !== 'td' && td.tagName.toLowerCase() !== 'th') return;
        if (!td.hasAttribute('data-label')) td.setAttribute('data-label', headers[i] || '');
        if (!td.querySelector('.value')) {
          const wrapper = document.createElement('span');
          wrapper.className = 'value';
          // Move existing children into wrapper
          while (td.firstChild) wrapper.appendChild(td.firstChild);
          td.appendChild(wrapper);
        }
      });
    });

    // Also handle nested responsive tables (e.g. details tables)
    table.querySelectorAll('table.responsive').forEach(function (nested) {
      if (nested === table) return;
      const nh = nested.querySelectorAll('thead th');
      const nheaders = Array.from(nh).map(h => h.textContent.trim());
      nested.querySelectorAll('tbody tr').forEach(function (ntr) {
        Array.from(ntr.children).forEach(function (ntd, i) {
          if (ntd.tagName.toLowerCase() !== 'td' && ntd.tagName.toLowerCase() !== 'th') return;
          if (!ntd.hasAttribute('data-label')) ntd.setAttribute('data-label', nheaders[i] || '');
          if (!ntd.querySelector('.value')) {
            const wrap = document.createElement('span');
            wrap.className = 'value';
            while (ntd.firstChild) wrap.appendChild(ntd.firstChild);
            ntd.appendChild(wrap);
          }
        });
      });
    });
  }

  function runOnLoad() {
    document.querySelectorAll('table.responsive').forEach(injectForTable);
  }

  // Expose helper for runtime DOM updates
  window.svtInjectLabels = function (table) {
    if (!table) {
      // If no table provided, run for all
      document.querySelectorAll('table.responsive').forEach(injectForTable);
      return;
    }
    // If a tbody or tbody id was passed, get nearest table
    if (table.tagName && table.tagName.toLowerCase() === 'tbody') table = table.closest('table');
    if (typeof table === 'string') table = document.querySelector(table);
    injectForTable(table);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runOnLoad);
  } else {
    runOnLoad();
  }
})();
