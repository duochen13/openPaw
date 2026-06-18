const QUICKCHART_BASE = 'https://quickchart.io/chart';
const BAR_COLOR = '#2563eb';

// holdings: [{ symbol, peRatio }]
// Returns a QuickChart.io bar-chart URL of current P/E per symbol, or null if no
// holding has a usable P/E value (e.g. P/E data unavailable from the source).
function buildPeBarChartUrl(holdings) {
  const usable = (holdings || []).filter(h => typeof h.peRatio === 'number' && Number.isFinite(h.peRatio));
  if (usable.length === 0) return null;

  const labels = usable.map(h => h.symbol);
  const data = usable.map(h => Number(h.peRatio.toFixed(1)));

  // Clean styling: faint horizontal gridlines, hidden vertical gridlines, no
  // border, no legend (single series), white background.
  const config = {
    type: 'bar',
    data: { labels, datasets: [{ label: 'P/E ratio', data, backgroundColor: BAR_COLOR, borderWidth: 0 }] },
    options: {
      layout: { padding: 8 },
      title: { display: true, text: 'P/E Ratio by Symbol', fontSize: 15, fontColor: '#1f2937' },
      legend: { display: false },
      scales: {
        yAxes: [{
          scaleLabel: { display: true, labelString: 'P/E ratio', fontColor: '#6b7280' },
          gridLines: { color: 'rgba(0,0,0,0.06)', drawBorder: false },
          ticks: { beginAtZero: true, fontColor: '#6b7280' }
        }],
        xAxes: [{
          gridLines: { display: false, drawBorder: false },
          ticks: { fontColor: '#6b7280' }
        }]
      }
    }
  };

  return `${QUICKCHART_BASE}?w=600&h=300&bkg=white&c=${encodeURIComponent(JSON.stringify(config))}`;
}

module.exports = { buildPeBarChartUrl };
