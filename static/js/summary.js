/* Графики сводки за период.
   Данные приходят из шаблона через json_script, поэтому в разметке
   нет ни одного значения — только идентификаторы.
   Цвета совпадают с палитрой страниц, то есть с брендбуком. */

(function () {
    'use strict';

    var COLOR = {
        blue: '#00326E',
        blueLight: '#0078AF',
        green: '#4BAF46',
        grey: '#6E6E6E',
        line: '#DDE3EA'
    };

    function read(id) {
        var node = document.getElementById(id);
        return node ? JSON.parse(node.textContent) : null;
    }

    function ru(value) {
        if (value === null || value === undefined) {
            return '—';
        }
        return value.toLocaleString('ru-RU', {maximumFractionDigits: 1});
    }

    Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = COLOR.grey;

    function daily(data) {
        var canvas = document.getElementById('chart-daily');
        if (!canvas || !data) {
            return;
        }
        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Добыча, т',
                        data: data.fact,
                        backgroundColor: COLOR.blue,
                        borderRadius: 2,
                        order: 2
                    },
                    {
                        label: 'План БП, т',
                        data: data.plan,
                        type: 'line',
                        borderColor: COLOR.green,
                        borderWidth: 2,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        // Разрыв на пропущенных сутках виден, а не сглажен:
                        // отсутствие данных нельзя выдавать за ровную линию.
                        spanGaps: false,
                        order: 1
                    }
                ]
            },
            options: {
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    y: {
                        beginAtZero: false,
                        grid: {color: COLOR.line},
                        ticks: {callback: ru}
                    },
                    x: {grid: {display: false}}
                },
                plugins: {
                    legend: {position: 'bottom'},
                    tooltip: {
                        callbacks: {
                            label: function (item) {
                                if (item.raw === null) {
                                    return 'нет данных за эти сутки';
                                }
                                return item.dataset.label + ': ' + ru(item.raw);
                            }
                        }
                    }
                }
            }
        });
    }

    function horizontal(id, data, label) {
        var canvas = document.getElementById(id);
        if (!canvas || !data || !data.labels.length) {
            return;
        }
        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: label,
                    data: data.values,
                    backgroundColor: COLOR.blueLight,
                    borderRadius: 2
                }]
            },
            options: {
                indexAxis: 'y',
                maintainAspectRatio: false,
                scales: {
                    x: {grid: {color: COLOR.line}, ticks: {callback: ru}},
                    y: {grid: {display: false}}
                },
                plugins: {
                    legend: {display: false},
                    tooltip: {
                        callbacks: {
                            label: function (item) {
                                return ru(item.raw) + ' т';
                            }
                        }
                    }
                }
            }
        });
    }

    daily(read('data-daily'));
    horizontal('chart-fields', read('data-fields'), 'Добыча, т');
    horizontal('chart-reasons', read('data-reasons'), 'Потери, т');
}());
