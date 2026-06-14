const QUICKCHART_BASE = 'https://quickchart.io/chart';
const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

// holdings: [{ symbol, series: [{ date, cumulativeReturnPct }] }]
// Returns a QuickChart.io image URL, or null if nothing chartable.
function buildReturnChartUrl(holdings) {
  const usable = (holdings || []).filter(h => Array.isArray(h.series) && h.series.length > 0);
  if (usable.length === 0) return null;

  // Use the longest series' dates as the shared x-axis labels.
  const longest = usable.reduce((best, h) => (h.series.length > best.series.length ? h : best), usable[0]);
  const labels = longest.series.map(p => p.date);

  const datasets = usable.map((h, i) => ({
    label: h.symbol,
    data: h.series.map(p => Number(p.cumulativeReturnPct.toFixed(2))),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length],
    fill: false,
    pointRadius: 0,          // clean line, no dots (Google Finance look)
    borderWidth: 2,
    lineTension: 0.3         // smooth curve
  }));

  // Google-Finance-inspired clean styling: faint horizontal gridlines,
  // hidden vertical gridlines, no border, compact bottom legend, white bg.
  const config = {
    type: 'line',
    data: { labels, datasets },
    options: {
      layout: { padding: 8 },
      title: { display: true, text: 'YTD Cumulative Return', fontSize: 15, fontColor: '#1f2937' },
      legend: { position: 'bottom', labels: { boxWidth: 12, fontSize: 11, fontColor: '#374151' } },
      scales: {
        yAxes: [{
          scaleLabel: { display: true, labelString: 'YTD return %', fontColor: '#6b7280' },
          gridLines: { color: 'rgba(0,0,0,0.06)', drawBorder: false, zeroLineColor: 'rgba(0,0,0,0.15)' },
          ticks: { fontColor: '#6b7280' }
        }],
        xAxes: [{
          gridLines: { display: false, drawBorder: false },
          ticks: { fontColor: '#6b7280', maxTicksLimit: 8, maxRotation: 0 }
        }]
      }
    }
  };

  return `${QUICKCHART_BASE}?w=600&h=300&bkg=white&c=${encodeURIComponent(JSON.stringify(config))}`;
}

module.exports = { buildReturnChartUrl };
