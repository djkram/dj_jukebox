(function () {
  function normStr(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  // SongFilter.init(inputEl, opts)
  // opts.rows     — CSS selector for the row/card elements to show/hide
  // opts.fields   — function(row) -> [str, ...] — strings to search in
  // opts.noResults — optional element shown when query returns 0 results
  // opts.onUpdate  — optional callback(rawQuery, visibleCount) for page-specific extras
  function init(inputEl, opts) {
    if (!inputEl) return;
    inputEl.addEventListener('input', function () {
      var rawQuery = inputEl.value.trim();
      var q = normStr(rawQuery);
      var rows = document.querySelectorAll(opts.rows);
      var visibleCount = 0;

      rows.forEach(function (row) {
        var isMatch = opts.fields(row).some(function (f) {
          return normStr(f).includes(q);
        });
        row.style.display = isMatch ? '' : 'none';
        if (isMatch) visibleCount++;
      });

      if (opts.noResults) {
        opts.noResults.classList.toggle('d-none', !(rawQuery && visibleCount === 0));
      }
      if (opts.onUpdate) {
        opts.onUpdate(rawQuery, visibleCount);
      }
    });
  }

  window.SongFilter = { init: init, normStr: normStr };
}());
