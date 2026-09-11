/* Графики дашборда руководства.
   Данные приходят из шаблона через json_script: в разметке нет ни
   одного значения, только идентификаторы.
   Цвета — из палитры страниц, то есть из корпоративного брендбука. */

(function () {
    'use strict';

    var COLOR = {
        blue: '#00326E',
        blueLight: '#0078AF',
        green: '#4BAF46',
        greenDark: '#0A8F2D',
        greenLight: '#9BC855',
        lime: '#D2DC78',
        grey: '#6E6E6E',
        red: '#C0392B',
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

    /* Выполнение бизнес-плана нарастающим итогом. */
    function progress(data) {
        var canvas = document.getElementById('chart-progress');
        if (!canvas || !data || !data.labels.length) {
            return;
        }
        new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Факт нарастающим, т',
                        data: data.fact,
                        borderColor: COLOR.blue,
                        backgroundColor: 'rgba(0, 50, 110, .08)',
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: true,
                        tension: 0.2
                    },
                    {
                        label: 'План БП нарастающим, т',
                        data: data.plan,
                        borderColor: COLOR.green,
                        borderWidth: 2,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        tension: 0.2
                    }
                ]
            },
            options: {
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    y: {grid: {color: COLOR.line}, ticks: {callback: ru}},
                    x: {grid: {display: false}}
                },
                plugins: {
                    legend: {position: 'bottom'},
                    tooltip: {
                        callbacks: {
                            label: function (item) {
                                return item.dataset.label + ': ' + ru(item.raw);
                            }
                        }
                    }
                }
            }
        });
    }

    /* Суточная добыча с планом. */
    function trend(data) {
        var canvas = document.getElementById('chart-trend');
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
                        // Разрыв на пропущенных сутках виден, а не сглажен.
                        spanGaps: false,
                        order: 1
                    }
                ]
            },
            options: {
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    y: {beginAtZero: false, grid: {color: COLOR.line},
                        ticks: {callback: ru}},
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

    /* Потери по составляющим, столбцами друг на друге. */
    function losses(data) {
        var canvas = document.getElementById('chart-losses');
        if (!canvas || !data) {
            return;
        }
        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Текущий простой',
                        data: data.downtime,
                        backgroundColor: COLOR.blue
                    },
                    {
                        label: 'Бездействие',
                        data: data.idle,
                        backgroundColor: COLOR.blueLight
                    },
                    {
                        label: 'Внутрисменные',
                        data: data.vsp,
                        backgroundColor: COLOR.greenLight
                    }
                ]
            },
            options: {
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    x: {stacked: true, grid: {display: false}},
                    y: {stacked: true, grid: {color: COLOR.line},
                        ticks: {callback: ru}}
                },
                plugins: {
                    legend: {position: 'bottom'},
                    tooltip: {
                        callbacks: {
                            label: function (item) {
                                return item.dataset.label + ': ' + ru(item.raw);
                            }
                        }
                    }
                }
            }
        });
    }

    /* Причины простоя за месяц. */
    function reasons(data) {
        var canvas = document.getElementById('chart-reasons');
        if (!canvas || !data || !data.labels.length) {
            return;
        }
        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: [COLOR.blue, COLOR.blueLight,
                        COLOR.greenDark, COLOR.green, COLOR.greenLight,
                        COLOR.lime],
                    borderWidth: 0
                }]
            },
            options: {
                maintainAspectRatio: false,
                cutout: '58%',
                plugins: {
                    legend: {position: 'right'},
                    tooltip: {
                        callbacks: {
                            label: function (item) {
                                return item.label + ': ' + ru(item.raw) + ' т';
                            }
                        }
                    }
                }
            }
        });
    }

    var series = read('data-trend');
    progress(read('data-progress'));
    trend(series);
    losses(series);
    reasons(read('data-reasons'));
}());
