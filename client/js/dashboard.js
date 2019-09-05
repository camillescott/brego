const socket = new WebSocket('ws://10.241.147.135:6565');

// Connection opened
socket.addEventListener('open', function(event) {
    socket.send("");
});

socket.onmessage = function(event) {
    //var d = JSON.parse(event.data);
    console.log(event.data);
};
