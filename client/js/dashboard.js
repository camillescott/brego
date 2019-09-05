const socket = new WebSocket('ws://192.168.1.54:6565');

// Connection opened
socket.addEventListener('open', function(event) {
    socket.send("1A37F239BC1");
});

socket.onmessage = function(event) {
    //var d = JSON.parse(event.data);
    console.log(event.data);
};
