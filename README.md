# Billy

Billy is a kind of AI agent middleman between the final user natural language prompts and the structured needs of a python application.


## Technologies
- Redis: used to save conversation information and lock users from flooding;
- RabbitMQ: used as means of communicating with the chat application;
- google-genai: to generate responses from AI asynchronously;
## Running Locally

Clone the project

```bash
git clone git@github.com:marquesch/whatsapp-worker.git
```

Go to the project directory

```bash
cd billy
```

Copy .env.example to .env
``` bash
cp .env.example .env
```

Add `AI_PLATFORM_API_KEY` and `LLM_MODEL` env values.

Run container
```bash
docker compose up
```

Send messages to RabbitMQ with relevant data.

Feel free to use [whatsapp-worker](https://github.com/marquesch/whatsapp-worker) for it.
## Contributing

Contributions are always welcome!

If you think you could improve it in any way, feel free to open a Pull Request and I'll be glad to review it!

