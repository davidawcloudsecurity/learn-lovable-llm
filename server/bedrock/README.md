### How to kill persistent service
```
PM2_HOME=/etc/.pm2 pm2 list
PM2_HOME=/etc/.pm2 pm2 stop all
PM2_HOME=/etc/.pm2 pm2 delete all
```
6️⃣ Where the logs are

Since PM2_HOME=/etc/.pm2

Logs are likely here:

ls /etc/.pm2/logs

Typical files:

bedrock-api-error.log
bedrock-api-out.log

View logs:

pm2 logs bedrock-api

or

tail -f /etc/.pm2/logs/bedrock-api-out.log

Since your process is managed by **PM2**, you just need to **restart the PM2 app** so it reloads the `.env` variables.

Your service name is:

```
bedrock-api
```

---

# 1️⃣ Restart the service

```bash
sudo PM2_HOME=/etc/.pm2 pm2 restart bedrock-api
```

or using the id:

```bash
sudo PM2_HOME=/etc/.pm2 pm2 restart 0
```

---

# 2️⃣ If the `.env` variables are loaded at startup

Some apps load environment variables **only when the process starts**. Restarting is enough.

But if PM2 also manages env variables, use:

```bash
sudo PM2_HOME=/etc/.pm2 pm2 restart bedrock-api --update-env
```

This forces PM2 to reload environment variables.

---

# 3️⃣ Verify it restarted

```bash
sudo PM2_HOME=/etc/.pm2 pm2 list
```

You should see the **restart counter increase**:

```
↺ 1
```

---

# 4️⃣ Check logs to confirm `.env` changes applied

```bash
sudo PM2_HOME=/etc/.pm2 pm2 logs bedrock-api
```

or directly:

```bash
tail -f /etc/.pm2/logs/bedrock-api-out.log
```

---

# 5️⃣ If the process fails after `.env` change

Check error logs:

```bash
tail -f /etc/.pm2/logs/bedrock-api-error.log
```

---

✅ **Quick command (most common):**

```bash
sudo PM2_HOME=/etc/.pm2 pm2 restart bedrock-api --update-env
```
