/* 强积金成分基金资料库 — 表格排序与筛选（原生 JS，无依赖）
   本文件由 scripts/build_pages.py 生成。 */
(function () {
  'use strict';

  var collator = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('zh-Hans', { numeric: true })
    : null;

  function cellValue(cell) {
    var v = cell.getAttribute('data-v');
    return v === null ? cell.textContent.trim() : v;
  }

  function compare(a, b, index, type, dir) {
    var va = cellValue(a.cells[index]);
    var vb = cellValue(b.cells[index]);
    var ea = va === '';
    var eb = vb === '';
    if (ea && eb) return 0;
    if (ea) return 1;          /* 空值永远排在最后 */
    if (eb) return -1;
    if (type === 'num') {
      var na = parseFloat(va);
      var nb = parseFloat(vb);
      if (isNaN(na) && isNaN(nb)) return 0;
      if (isNaN(na)) return 1;
      if (isNaN(nb)) return -1;
      return (na - nb) * dir;
    }
    return (collator ? collator.compare(va, vb) : (va < vb ? -1 : va > vb ? 1 : 0)) * dir;
  }

  function initSortable(table) {
    var headers = table.tHead ? table.tHead.rows[0].cells : [];
    Array.prototype.forEach.call(headers, function (th, index) {
      var type = th.getAttribute('data-type') || 'str';
      var btn = th.querySelector('.sort-btn') || th;
      btn.addEventListener('click', function () {
        var current = th.getAttribute('aria-sort');
        var dir = current === 'ascending' ? -1 : 1;
        Array.prototype.forEach.call(headers, function (other) {
          if (other.hasAttribute('aria-sort')) other.setAttribute('aria-sort', 'none');
        });
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) { return compare(a, b, index, type, dir); });
        var frag = document.createDocumentFragment();
        rows.forEach(function (r) { frag.appendChild(r); });
        tbody.appendChild(frag);
      });
    });
  }

  function initFilters(form, table) {
    var q = form.querySelector('#f-q');
    var ferMax = form.querySelector('#f-fer-max');
    var reset = form.querySelector('#f-reset');
    var status = form.querySelector('#f-status');
    var selects = Array.prototype.slice.call(form.querySelectorAll('[data-filter-key]'));
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var total = rows.length;

    function apply() {
      var needle = (q && q.value ? q.value : '').trim().toLowerCase();
      var limit = ferMax && ferMax.value !== '' ? parseFloat(ferMax.value) : null;
      var picks = selects.map(function (s) {
        return { key: s.getAttribute('data-filter-key'), value: s.value };
      });
      var shown = 0;
      rows.forEach(function (row) {
        var ok = true;
        if (needle && row.getAttribute('data-search').indexOf(needle) === -1) ok = false;
        if (ok) {
          for (var i = 0; i < picks.length; i++) {
            if (picks[i].value && row.getAttribute('data-' + picks[i].key) !== picks[i].value) {
              ok = false;
              break;
            }
          }
        }
        if (ok && limit !== null && !isNaN(limit)) {
          var fer = row.getAttribute('data-fer');
          if (fer === '' || parseFloat(fer) > limit) ok = false;
        }
        row.hidden = !ok;
        if (ok) shown++;
      });
      if (status) status.textContent = '显示 ' + shown + ' / ' + total + ' 只基金';
    }

    if (q) q.addEventListener('input', apply);
    if (ferMax) ferMax.addEventListener('input', apply);
    selects.forEach(function (s) { s.addEventListener('change', apply); });
    if (reset) {
      reset.addEventListener('click', function () {
        if (q) q.value = '';
        if (ferMax) ferMax.value = '';
        selects.forEach(function (s) { s.value = ''; });
        apply();
      });
    }
    apply();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var tables = document.querySelectorAll('table[data-sortable]');
    Array.prototype.forEach.call(tables, initSortable);
    var form = document.getElementById('filters');
    var table = document.getElementById('fund-table');
    if (form && table) initFilters(form, table);
  });
})();
