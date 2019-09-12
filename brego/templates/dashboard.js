var temperature_spec = {
  $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
  data: {name: 'table'},
  width: 500,
  mark: 'line',
  encoding: {
      x: {field: 'time', type: 'quantitative', scale: {zero: false}},
    y: {field: 'value', type: 'quantitative'},
    color: {field: 'sensor', type: 'nominal', legend: null}
  }
};

var adc_spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
    data: {name: 'table'},
//    width: 500,
    autosize: {
	  type: "fit",
	  resize: true,
	},
    mark: {
        type: 'line',
        strokeWidth: 3,
        clip: true
    },
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
        color: {field: 'sensor', type: 'nominal', legend: null}
    }
};


var start_time = new Date().getTime() / 1000.0;

function parseData(data) {
    var d = JSON.parse(event.data);
    var data = {}
    data['time'] = d.data.time - start_time;
    data['sensor'] = d.device;
    data['value'] = d.data.value;

    return data;
}


function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}


async function main() {

    vegaEmbed('#ADC',
              adc_spec,
              {theme: 'vox',
               renderer: 'svg',
               actions: false}).then(async function(result) {
        view = result.view;
        const socket = new WebSocket('ws://{{ request.host }}/sensors/stream/MCP3008-0');

        socket.onmessage = function(event) {
            var data = parseData(event.data)
            var changeSet = vega
              .changeset()
              .insert(data)
              .remove(function(t) {
                return t.time < data.time - 30.0;
              });
            var div = document.getElementById('adc-card');
            view.width(div.clientWidth * 0.9).runAsync();
            view.change('table', changeSet).runAsync();
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
