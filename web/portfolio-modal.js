/* Portfolio Detail Modal - handles opening/closing and data fetching */

let performanceChart = null;

async function openPortfolioModal(symbol) {
  try {
    const response = await fetch(`/api/portfolio/${symbol}/detail`);
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API error ${response.status}:`, errorText);
      alert(`Error loading portfolio: ${response.status} ${response.statusText}`);
      return;
    }
    const data = await response.json();

    // Update header
    document.getElementById('modalSymbol').textContent = data.symbol;
    document.getElementById('modalDescription').textContent = data.current.description || 'Position Details';

    // Update metrics
    const current = data.current;
    document.getElementById('metricQty').textContent = current.qty.toLocaleString('en-US', { maximumFractionDigits: 2 });
    document.getElementById('metricValue').textContent = '$' + current.market_value.toLocaleString('en-US', { maximumFractionDigits: 2 });

    const gainText = current.total_gain_dollar >= 0 ? '+' : '';
    document.getElementById('metricGain').textContent = gainText + '$' + current.total_gain_dollar.toLocaleString('en-US', { maximumFractionDigits: 2 });
    document.getElementById('metricGain').className = 'metric-value ' + (current.total_gain_dollar >= 0 ? 'positive' : 'negative');
    document.getElementById('gainCard').className = 'metric-card ' + (current.total_gain_dollar >= 0 ? 'positive' : 'negative');

    const pctText = current.avg_gain_pct >= 0 ? '+' : '';
    document.getElementById('metricGainPct').textContent = pctText + current.avg_gain_pct.toFixed(2) + '%';
    document.getElementById('metricGainPct').className = 'metric-value ' + (current.avg_gain_pct >= 0 ? 'positive' : 'negative');
    document.getElementById('gainPctCard').className = 'metric-card ' + (current.avg_gain_pct >= 0 ? 'positive' : 'negative');

    // Update period metrics (YTD and MTD)
    const periods = data.periods || {};
    const ytdDollarEl = document.getElementById('metricYtdDollar');
    const ytdPctEl = document.getElementById('metricYtdPct');
    const mtdDollarEl = document.getElementById('metricMtdDollar');
    const mtdPctEl = document.getElementById('metricMtdPct');

    if (ytdDollarEl && ytdPctEl && mtdDollarEl && mtdPctEl) {
      const ytdDollar = periods.ytd_dollar || 0;
      const ytdPct = periods.ytd_pct || 0;
      const mtdDollar = periods.mtd_dollar || 0;
      const mtdPct = periods.mtd_pct || 0;

      const ytdDollarText = ytdDollar >= 0 ? '+' : '';
      const ytdPctText = ytdPct >= 0 ? '+' : '';
      const mtdDollarText = mtdDollar >= 0 ? '+' : '';
      const mtdPctText = mtdPct >= 0 ? '+' : '';

      ytdDollarEl.textContent = ytdDollarText + '$' + Math.abs(ytdDollar).toLocaleString('en-US', { maximumFractionDigits: 2 });
      ytdDollarEl.className = 'metric-value ' + (ytdDollar >= 0 ? 'positive' : 'negative');

      ytdPctEl.textContent = ytdPctText + Math.abs(ytdPct).toFixed(2) + '%';
      ytdPctEl.className = 'metric-value ' + (ytdPct >= 0 ? 'positive' : 'negative');

      mtdDollarEl.textContent = mtdDollarText + '$' + Math.abs(mtdDollar).toLocaleString('en-US', { maximumFractionDigits: 2 });
      mtdDollarEl.className = 'metric-value ' + (mtdDollar >= 0 ? 'positive' : 'negative');

      mtdPctEl.textContent = mtdPctText + Math.abs(mtdPct).toFixed(2) + '%';
      mtdPctEl.className = 'metric-value ' + (mtdPct >= 0 ? 'positive' : 'negative');
    }

    // Show sale status if position was sold
    const saleStatusEl = document.getElementById('saleStatus');
    if (saleStatusEl && data.is_sold) {
      saleStatusEl.innerHTML = `
        <div style="padding: 12px; background: #fef2f2; border-left: 4px solid #ef4444; border-radius: 4px; margin-bottom: 16px;">
          <div style="font-size: 12px; color: #991b1b; text-transform: uppercase; font-weight: 600; margin-bottom: 4px;">Position Sold</div>
          <div style="font-size: 14px; color: #dc2626;">
            Realized Gain/Loss: ${data.realized_gains_total >= 0 ? '+' : ''}$${data.realized_gains_total.toLocaleString('en-US', { maximumFractionDigits: 2 })}
          </div>
        </div>
      `;
    }

    // Build chart
    buildChart(data.timeseries, data.current, data.date, data.is_sold);

    // Account breakdown
    const accountHTML = data.accounts.map(acc => `
      <div class="account-row">
        <span class="account-name">${acc.name}</span>
        <div style="text-align: right;">
          <div class="account-value">$${acc.total_value.toLocaleString('en-US', { maximumFractionDigits: 2 })}</div>
          <div style="font-size: 12px; color: #6b7280;">${acc.total_qty.toFixed(0)} shares</div>
        </div>
      </div>
    `).join('');
    document.getElementById('accountBreakdown').innerHTML = accountHTML || '<p>No accounts</p>';

    // Price history
    const historyHTML = data.timeseries.reverse().map((row, idx) => {
      const dailyChangeClass = row.daily_change > 0 ? 'positive' : row.daily_change < 0 ? 'negative' : '';
      const dailyChangeText = row.daily_change > 0 ? '+$' : '$';
      const gainClass = row.total_gain > 0 ? 'positive' : row.total_gain < 0 ? 'negative' : '';
      const gainText = row.total_gain > 0 ? '+$' : '$';
      return `
        <tr>
          <td class="date">${row.date}</td>
          <td>${row.qty.toFixed(0)}</td>
          <td>$${row.market_value.toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
          <td class="${dailyChangeClass}">${dailyChangeText}${Math.abs(row.daily_change).toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
          <td class="${gainClass}">${gainText}${Math.abs(row.total_gain).toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
        </tr>
      `;
    }).join('');
    document.getElementById('priceHistory').innerHTML = historyHTML;

    // Show modal
    document.getElementById('portfolioModal').classList.add('active');
  } catch (err) {
    console.error('Error loading portfolio detail:', err);
    alert('Error loading portfolio details');
  }
}

function closePortfolioModal() {
  document.getElementById('portfolioModal').classList.remove('active');
  if (performanceChart) {
    performanceChart.destroy();
    performanceChart = null;
  }
}

function switchTab(tabName) {
  // Hide all tabs
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

  // Show selected tab
  document.getElementById('tab-' + tabName).classList.add('active');
  event.target.classList.add('active');
}

function buildChart(timeseries, current, apiDate, isSold) {
  if (performanceChart) {
    performanceChart.destroy();
  }

  const ctx = document.getElementById('performanceChart').getContext('2d');
  const dates = timeseries.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
  const qty = timeseries.map(d => d.qty);
  const gains = timeseries.map(d => d.total_gain);

  // If position was sold, add a final data point showing 0 shares
  // This visualizes the drop to 0 on the chart
  if (isSold && current.qty === 0) {
    const today = new Date();
    const todayStr = today.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

    const lastDate = timeseries.length > 0 ? new Date(timeseries[timeseries.length - 1].date) : null;
    const isLastDateToday = lastDate &&
      lastDate.getFullYear() === today.getFullYear() &&
      lastDate.getMonth() === today.getMonth() &&
      lastDate.getDate() === today.getDate();

    // Add 0 shares point if not already at today
    if (!isLastDateToday) {
      dates.push(todayStr);
      qty.push(0);
      // Keep the current gain/loss (realized loss from the sale)
      gains.push(current.total_gain_dollar);
    }
  } else {
    // For active positions, add today's data if API is from today
    const today = new Date();
    const todayStr = today.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

    const apiDateTime = new Date(apiDate);
    const isApiFromToday =
      apiDateTime.getFullYear() === today.getFullYear() &&
      apiDateTime.getMonth() === today.getMonth() &&
      apiDateTime.getDate() === today.getDate();

    const lastDate = timeseries.length > 0 ? new Date(timeseries[timeseries.length - 1].date) : null;
    const isLastDateToday = lastDate &&
      lastDate.getFullYear() === today.getFullYear() &&
      lastDate.getMonth() === today.getMonth() &&
      lastDate.getDate() === today.getDate();

    // Add today's point only if API data is from today AND not already in timeseries
    if (isApiFromToday && !isLastDateToday) {
      dates.push(todayStr);
      qty.push(current.qty);
      gains.push(current.total_gain_dollar);
    }
  }

  // Determine gain line color based on final value (red if negative, green if positive)
  const finalGain = gains[gains.length - 1];
  const gainColor = finalGain >= 0 ? '#10b981' : '#ef4444';

  performanceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Shares Owned',
          data: qty,
          borderColor: '#667eea',
          backgroundColor: 'rgba(102, 126, 234, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          yAxisID: 'y',
          pointRadius: 2,
          pointBackgroundColor: '#667eea',
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointHoverRadius: 4
        },
        {
          label: 'Gain/Loss ($)',
          data: gains,
          borderColor: gainColor,
          backgroundColor: gainColor === '#10b981' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          yAxisID: 'y1',
          pointRadius: 2,
          pointBackgroundColor: gainColor,
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointHoverRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top' },
        tooltip: {
          backgroundColor: 'rgba(0,0,0,0.8)',
          padding: 12,
          titleFont: { size: 14, weight: 600 },
          bodyFont: { size: 13 },
          cornerRadius: 6,
          callbacks: {
            label: (context) => {
              if (context.dataset.yAxisID === 'y1') {
                return context.dataset.label + ': $' + context.raw.toLocaleString('en-US', { maximumFractionDigits: 2 });
              } else {
                return context.dataset.label + ': ' + context.raw.toLocaleString('en-US', { maximumFractionDigits: 0 }) + ' shares';
              }
            }
          }
        }
      },
      scales: {
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          title: { display: true, text: 'Shares Owned', font: { size: 12, weight: 600 } },
          beginAtZero: true,
          ticks: {
            callback: (value) => value.toLocaleString('en-US', { maximumFractionDigits: 0 })
          },
          grid: { color: 'rgba(0,0,0,0.05)' }
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          title: { display: true, text: 'Gain/Loss ($)', font: { size: 12, weight: 600 } },
          ticks: {
            callback: (value) => '$' + value.toLocaleString('en-US', { maximumFractionDigits: 0 })
          },
          grid: { drawOnChartArea: false }
        },
        x: {
          grid: { display: false }
        }
      }
    }
  });
}

// Close modal when clicking overlay
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('portfolioModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target.id === 'portfolioModal') {
        closePortfolioModal();
      }
    });
  }
});
