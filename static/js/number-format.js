(function () {
  'use strict';

  const formatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  });

  window.formatNumber = function formatNumber(value) {
    const number = Number(value ?? 0);
    return formatter.format(Number.isFinite(number) ? number : 0);
  };

  window.formatMoney = function formatMoney(value, symbol = '$') {
    return `${symbol}${window.formatNumber(value)}`;
  };
})();
