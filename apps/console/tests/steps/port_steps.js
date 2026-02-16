import { Given, Then } from "@cucumber/cucumber";
import net from "net";

const sockets = [];

function occupyPort(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(port, "0.0.0.0", () => {
      sockets.push(server);
      resolve();
    });
  });
}

Given("port {int} is occupied", async function (port) {
  await occupyPort(port);
});

Then("I release occupied ports", async function () {
  for (const server of sockets) {
    await new Promise((resolve) => server.close(resolve));
  }
  sockets.length = 0;
});
