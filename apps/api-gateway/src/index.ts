import dotenv from "dotenv";
dotenv.config();

import { app } from "./server.js";
import { connectDatabase } from "./config/db.js";

const PORT = process.env.PORT || 4000;

async function bootstrap() {
  try {
    await connectDatabase();
    console.log("[MongoDB] Connected to database successfully.");

    app.listen(PORT, () => {
      console.log(`[API-Gateway] Server listening on port ${PORT}`);
    });
  } catch (error) {
    console.error("[API-Gateway] Failed to start server:", error);
    process.exit(1);
  }
}

bootstrap();
