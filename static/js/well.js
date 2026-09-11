/* График потерь по суткам для одной скважины.
   Данные приходят из шаблона через json_script. */

(function () {
    'use strict';

    var COLOR = {blue: '#00326E', line: '#DDE3EA', grey: '#6E6E6E'};

    var node = document.getElementById('data-well');
    var canvas = document.getElementById('chart-well');
    if (!node || !canvas) {
        return;
    }
    var data = JSON.parse(node.textContent);

    function ru(value) {
        if (value === null || value === undefined) {
            return '—';
        }
        return value.toLocaleString('ru-RU', {maximumFractionDigits: 1});
    }

    Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
    Chart.defaults.color = COLOR.grey;

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Потери, т/сут',
                data: data.values,
                backgroundColor: COLOR.blue,
                borderRadius: 2
            }]
        },
        options: {
            maintainAspectRatio: false,
            scales: {
                y: {beginAtZero: true, grid: {color: COLOR.line},
                    ticks: {callback: ru}},
                x: {grid: {display: false}}
            },
            plugins: {
                legend: {display: false},
                tooltip: {
                    callbacks: {
                        label: function (item) {
                            // Пустые сутки означают, что скважина работала,
                            // а не что потери были нулевыми.
                            if (item.raw === null) {
                                return 'скважина работала';
                            }
                            return ru(item.raw) + ' т/сут';
                        }
                    }
                }
            }
        }
    });
}());
