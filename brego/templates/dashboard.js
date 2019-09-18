var start_time = new Date().getTime()

function parseData(data) {
    var raw = JSON.parse(event.data);
    var data = raw.map(function(reading) {
        entry = {'time': new Date(reading[0] * 1000)}
        entry[reading[1]] = reading[2];
        return entry;
    });
    
    return data;
}

function getContainerSize(elem_name) {
    var size = {};
    var container = document.getElementById(elem_name);
    size['width'] = container.clientWidth;
    size['height'] = container.clientHeight * 0.95;
    return size;
}


function adc_chart(elem_name) {
    var data = [];
    var size = getContainerSize('ADC');
    var chart = realTimeLineChart(0.0, 1.0, ['Potentiometer'])
                .width(size.width);

    const socket = new WebSocket('ws://{{ request.host }}/sensors/stream/Potentiometer');


    function resize() {
        if (d3.select(elem__name + " svg").empty()) {
            return;
        }
        chart.width(+d3.select(elem_name).style("width").replace(/(px)/g, ""));
        d3.select(elem_name).call(chart);
    }

    socket.onmessage = function(event) {
        var parsed = parseData(event.data)
        parsed.forEach(function(reading) {
            data.push(reading);
            if(reading.time - data[0]['time'] > 5000) {
                data.shift();
            }
        });
        console.log(data);

        d3.select(elem_name).datum(data).call(chart);
    }

    document.addEventListener("DOMContentLoaded", function() {
        d3.select(elem_name).datum(data).call(chart);
        d3.select(window).on('resize', resize);
    });
}


function temps_chart(elem_name) {
    var data = [];
    var size = getContainerSize('temperatures');
    var chart = realTimeLineChart(0.0, 50.0, ['value'])
                .width(size.width);

    const socket = new WebSocket('ws://{{ request.host }}/sensors/stream/Potentiometer');


    function resize() {
        if (d3.select(elem__name + " svg").empty()) {
            return;
        }
        chart.width(+d3.select(elem_name).style("width").replace(/(px)/g, ""));
        d3.select(elem_name).call(chart);
    }

    socket.onmessage = function(event) {
        var msg = parseData(event.data)
        data.push(msg);

        if(msg['time'] - data[0]['time'] > 60000.0) {
            data.shift();
        }

        d3.select(elem_name).datum(data).call(chart);
    }

    document.addEventListener("DOMContentLoaded", function() {
        d3.select(elem_name).datum(data).call(chart);
        d3.select(window).on('resize', resize);
    });
}


adc_chart('#ADC');
//temps_chart('#temperatures');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

