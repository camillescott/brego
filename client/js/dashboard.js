/*
var temperature_spec = {
  $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
  data: {name: 'table'},
  width: 500,
  mark: 'line',
  encoding: {
      x: {field: 'time', type: 'quantitative', scale: {zero: false}},
    y: {field: 'value', type: 'quantitative'},
    color: {field: 'sensor', type: 'nominal'}
  }
};

var adc_spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
    data: {name: 'table'},
    width: 500,
    mark: {
        type: 'line',
        clip: true},
    encoding: {
        x: {
            field: 'time', 
            type: 'quantitative', 
            scale: {zero: false}
        },
        y: {
            field: 'value', 
            type: 'quantitative',
            scale: {domain: [0.0, 1.0]}
        },
    color: {field: 'sensor', type: 'nominal'}
  }
};
*/

var dashboard_spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
    data: {name: 'table'},
    width: 500,
    vconcat: [
        {
            mark: {
                type: 'line',
                clip: true},
            encoding: {
                x: {
                    field: 'time', 
                    type: 'quantitative', 
                    scale: {zero: false}
                },
                y: {
                    field: 'MCP3008_0', 
                    type: 'quantitative',
                    scale: {domain: [0.0, 1.0]},
                    impute: {
                        method: "mean",
                        frame: [-5, 5]
                    }
                },
            }
        },
        {
            mark: {
                type: 'line',
                clip: true},
            encoding: {
                x: {
                    field: 'time', 
                    type: 'quantitative', 
                    scale: {zero: false}
                },
                y: {
                    field: '28_011454fc03aa', 
                    type: 'quantitative'
                    //,
                    //impute: {
                    //    method: "mean",
                    //    frame: [-1, 0]
                    //}
                },
            }
        }
    ]
};

const socket = new WebSocket('ws://192.168.1.54:8080/sensors/stream/websocket');
var start_time = new Date().getTime() / 1000.0;

function parseData(data) {
    var d = JSON.parse(event.data);
    var device = d.device.replace('-', '_');
    var data = d.data;
    data['time'] = data.time - start_time;

    var row = {'time': data.time};
    row[device] = data.value;

    return row;
}


function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

var buffer = [];
socket.onopen = function(event) {
    socket.onmessage = function(event) {
        var row = parseData(event.data);
        buffer.push(row);
    }
}

async function main() {


    while(buffer.length < 100) {
        await sleep(1);
    }

    var running = true;

    vegaEmbed('#dashboard', dashboard_spec).then(async function(result) {
        view = result.view;

        // add the buffered messages to the view
        var changeSet = vega
            .changeset()
            .insert(buffer);
        view.change('table', changeSet).runAsync();

        // set a new onmessage callback
        while(running) {
            var row = buffer.pop();
            console.log(row);
            var changeSet = vega
              .changeset()
              .insert(row)
              .remove(function(t) {
                return t.time < row.time - 30.0;
              });
            view.change('table', changeSet).runAsync();
            await sleep(50);
        }
    });
}

main();

/*
vegaEmbed('#temperatures', temperature_spec).then(function(result) {
    temps_view = result.view;

    vegaEmbed('#adcs', adc_spec).then(function(result2) {
        adcs_view = result2.view;

        socket.onopen = function(event) {

            socket.onmessage = function(event) {
                var d = JSON.parse(event.data);
                var device = d.device;
                var data = d.data;
                console.log(d);
                data['time'] = data.time - start_time;



                if (device == 'MCP3008-0') {
                    var changeSet = vega
                      .changeset()
                      .insert({'time': data.time, 'value': data.value, 'sensor': device})
                      .remove(function(t) {
                        return t.time < data.time - 30.0;
                      });
                    adcs_view.change('table', changeSet).runAsync();
                } else {
                    var changeSet = vega
                      .changeset()
                      .insert({'time': data.time, 'value': data.value, 'sensor': device})
                      .remove(function(t) {
                        return t.time < data.time - 30.0;
                      });
                    temps_view.change('table', changeSet).runAsync();
                }
            }
        }
    });
});

*/
