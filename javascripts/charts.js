// Chart.js integration for AGON benchmarks
// This script creates interactive visualizations for benchmark data

document.addEventListener('DOMContentLoaded', function() {
  // Only run on benchmarks page
  if (!window.benchmarkData) {
    return;
  }

  const data = window.benchmarkData.datasets;

  // AGON color palette
  const colors = {
    primary: '#0066CC',
    primaryDark: '#003D7A',
    primaryLight: '#3399FF',
    accent: '#FF9500',
    success: '#00C853',
    warning: '#FF9500',
    json: '#403535ff',
    text: '#0066CC',
    columns: '#3399FF',
    struct: '#00C853'
  };

  // Medium gray for legend/labels to stay readable in light and dark
  const accentText = '#777777';

  // Chart: Savings vs Pretty JSON (Vertical Bar Chart)
  const savingsCtx = document.getElementById('savingsChart');
  if (savingsCtx) {
    const labels = data.map(d => d.name);
    const autoFormats = data.map(d => d.auto_format);

    // Display savings vs Pretty JSON; keep Compact JSON for threshold context
    const compactSavings = data.map(d => ((d.pretty - d.compact) / d.pretty * 100));
    const textSavings = data.map(d => ((d.pretty - d.text) / d.pretty * 100));
    const columnsSavings = data.map(d => ((d.pretty - d.columns) / d.pretty * 100));
    const structSavings = data.map(d => ((d.pretty - d.struct) / d.pretty * 100));
    const autoSavings = data.map(d => ((d.pretty - d.auto_tokens) / d.pretty * 100));

    // Color bars based on positive/negative savings
    const autoColors = autoSavings.map(s => s >= 0 ? colors.success : colors.warning);
    const textColors = textSavings.map(s => s >= 0 ? 'rgba(0, 102, 204, 0.7)' : 'rgba(255, 149, 0, 0.7)');
    const columnsColors = columnsSavings.map(s => s >= 0 ? 'rgba(51, 153, 255, 0.7)' : 'rgba(255, 149, 0, 0.7)');
    const structColors = structSavings.map(s => s >= 0 ? 'rgba(0, 200, 83, 0.7)' : 'rgba(255, 149, 0, 0.7)');

    new Chart(savingsCtx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Compact JSON (baseline)',
            data: compactSavings,
            backgroundColor: 'rgba(102, 102, 102, 0.35)',
            borderColor: colors.json,
            borderWidth: 1,
            stack: 'baseline'
          },
          {
            label: 'AGONText',
            data: textSavings,
            backgroundColor: textColors,
            borderColor: colors.text,
            borderWidth: 1
          },
          {
            label: 'AGONColumns',
            data: columnsSavings,
            backgroundColor: columnsColors,
            borderColor: colors.columns,
            borderWidth: 1
          },
          {
            label: 'AGONStruct',
            data: structSavings,
            backgroundColor: structColors,
            borderColor: colors.success,
            borderWidth: 1
          },
          {
            label: 'Auto Selected (Winner)',
            data: autoSavings,
            backgroundColor: autoColors,
            borderColor: colors.accent,
            borderWidth: 3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: 'Token Savings vs Pretty JSON (%)',
            color: accentText,
            font: {
              size: 18,
              weight: 'bold'
            },
            padding: 20
          },
          subtitle: {
            display: true,
            text: 'Auto selection uses compact JSON to apply min_savings; savings shown here are vs pretty JSON',
            color: accentText,
            font: {
              size: 12
            },
            padding: { bottom: 10 }
          },
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              color: accentText,
              padding: 15,
              font: {
                size: 12
              }
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                const value = context.parsed.y.toFixed(1);
                const sign = value >= 0 ? '+' : '';
                if (context.dataset.label.startsWith('Auto')) {
                  const fmt = autoFormats[context.dataIndex];
                  return `Winning Format: ${fmt}: ${sign}${value}% `;
                }
                return `${context.dataset.label}: ${sign}${value}%`;
              },
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Dataset',
              color: accentText,
              font: {
                size: 14,
                weight: 'bold'
              }
            },
            ticks: {
              color: accentText
            }
          },
          y: {
            title: {
              display: true,
              text: 'Savings vs Pretty JSON (%)',
              color: accentText,
              font: {
                size: 14,
                weight: 'bold'
              }
            },
            ticks: {
              color: accentText,
              callback: function(value) {
                const sign = value >= 0 ? '+' : '';
                return `${sign}${value.toFixed(0)}%`;
              }
            },
            // Add a horizontal line at 0%
            grid: {
              color: function(context) {
                if (context.tick.value === 0) {
                  return 'rgba(0, 0, 0, 0.5)';
                }
                return 'rgba(0, 0, 0, 0.1)';
              },
              lineWidth: function(context) {
                if (context.tick.value === 0) {
                  return 2;
                }
                return 1;
              }
            }
          }
        }
      }
    });
  }
});
