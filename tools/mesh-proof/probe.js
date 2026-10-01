const net = require("node:net");
const tls = require("node:tls");

const TIMEOUT = 3000;
const H2_PREFACE = Buffer.concat([
  Buffer.from("PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"),
  Buffer.from([0, 0, 0, 4, 0, 0, 0, 0, 0]),
]);

function probe(check) {
  return new Promise((resolve) => {
    let settled = false;
    let socket = null;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      if (socket) socket.destroy();
      resolve([check.id, ok]);
    };
    if (check.kind === "h2c") {
      socket = net.connect({ host: check.host, port: check.port });
      socket.on("connect", () => socket.write(H2_PREFACE));
      socket.on("data", () => finish(true));
      socket.on("error", () => finish(false));
    } else {
      socket = tls.connect({ host: check.host, port: check.port, rejectUnauthorized: false });
      socket.on("secureConnect", () => finish(true));
      socket.on("error", (err) => finish(typeof err.code === "string" && err.code.startsWith("ERR_SSL")));
    }
    socket.on("close", () => finish(false));
    socket.setTimeout(TIMEOUT, () => finish(false));
  });
}

const checks = JSON.parse(process.argv[process.argv.length - 1]);
Promise.all(checks.map(probe)).then((results) => {
  console.log(JSON.stringify(Object.fromEntries(results)));
});
