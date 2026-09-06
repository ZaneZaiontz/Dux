# Dux
Dux is a LLM-based application to help developers type/talk through their coding problems, assisting with bring ideas to reality, and planning your project


## Setting up Dux

To setup Dux, make sure you have at a minimum docker installed onto your system. You can do so here https://www.docker.com/get-started/

Once docker is installed and functioning, navigate from the project root directory to /docker/backend/ and copy the `env_temp` to `.env`. Then open the `.env` file you just created and change whatever you need to. At a minimal you need to add in a key for `GEMINI_KEY`. You can get one from https://aistudio.google.com/app/api-keys for free if you sign up and create a project.

Once that's done, you can run the project by using the script in /docker/backend/ `./start.sh` or from that folder location you can run `docker compose up`

This starts a Postgres database alongside the backend. Your conversations are stored there, so Dux remembers where you left off after a restart.

## Pointing Dux at your code

Dux answers better when it can read the project you are stuck on. Set `DUX_WORKSPACE`
in your `.env` to the folder you want it to read, then restart. It defaults to the Dux
project itself, so it works out of the box.

The folder is mounted read-only, and Dux will not open secrets such as `.env` files or
keys, anything your `.gitignore` covers, or dependency folders like `node_modules`.

## Testing Dux

To test to make sure Dux is working, you can use a provided script to hit the server and ask questions. 

***This is a temporary solution until the frontend has been developed***

From the project root directory, navigate to /tools/ and run either `./chat.py` or `./chat.sh` as they both do the same thing. This should allow you to talk to Dux and ask questions.
