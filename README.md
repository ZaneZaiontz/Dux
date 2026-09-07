# Dux
Dux is a LLM-based application to help developers type/talk through their coding problems, assisting with bring ideas to reality, and planning your project


## Setting up Dux

To setup Dux, make sure you have at a minimum docker installed onto your system. You can do so here https://www.docker.com/get-started/

Once docker is installed and functioning, navigate from the project root directory to /docker/backend/ and copy the `env_temp` to `.env`. Then open the `.env` file you just created and change whatever you need to.

Dux talks to any OpenAI compatible endpoint, so it runs against a local model by default and against a cloud model if you would rather. The settings that matter are:

- `DUX_MODEL` - the model name your server expects. Leave it empty and Dux will
  ask the server which model it has loaded, which also tells Dux how big a context
  window it has to work with
- `DUX_MODEL_BASE_URL` - where the server is, ending in `/v1`
- `DUX_MODEL_KEY` - your API key, or anything at all for a local server that ignores it

For a local server such as LM Studio, keep the default `http://host.docker.internal:1234/v1`. Dux runs in a container, so `localhost` would point at the container rather than at your machine, and `host.docker.internal` is how it reaches you. Your model server also has to listen on your network rather than only on localhost, which in LM Studio is the "Serve on Local Network" setting.

For a cloud model, set `DUX_MODEL_BASE_URL` to that provider's OpenAI compatible URL and put your real key in `DUX_MODEL_KEY`.

Once that's done, you can run the project by using the script in /docker/backend/ `./start.sh` or from that folder location you can run `docker compose up`

This starts a Postgres database alongside the backend. Your conversations are stored there, so Dux remembers where you left off after a restart.

## Pointing Dux at your code

Dux answers better when it can read the project you are stuck on. Set `DUX_WORKSPACE`
in your `.env` to the folder you want it to read, then restart. It defaults to the Dux
project itself, so it works out of the box.

The folder is mounted read-only, and Dux will not open secrets such as `.env` files or
keys, anything your `.gitignore` covers, or dependency folders like `node_modules`.

## Seeing what Dux is doing

Every run is traced. Each graph step, model call and file read becomes a span, so you
can see where a slow turn actually went.

- Phoenix, at http://localhost:6006, is the one to open first. It shows the prompt and
  the reply for every model call, which is how you tell why Dux reached the conclusion
  it did.
- Grafana, at http://localhost:3000, reads the same traces from Tempo and is the place
  for timing across many turns.

Both receive the same traces, because the app sends them once to a collector that
forwards them to each. Turning either off is a change to the collector settings and
never to the code.

## Testing Dux

To test to make sure Dux is working, you can use a provided script to hit the server and ask questions. 

***This is a temporary solution until the frontend has been developed***

From the project root directory, navigate to /tools/ and run `./chat.py`. This lets you talk to Dux and ask questions.

Dux tells you what it is doing while it works, so you can see it thinking about your problem and reading your code, then watch the reply appear a word at a time.
