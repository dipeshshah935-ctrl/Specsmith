import mongoose from "mongoose";

export async function connectDatabase(uri?: string): Promise<typeof mongoose> {
  const resolvedUri = uri ?? process.env.MONGODB_URI;
  if (!resolvedUri) {
    throw new Error("MONGODB_URI environment variable is required");
  }

  return await mongoose.connect(resolvedUri);
}

export async function disconnectDatabase(): Promise<void> {
  await mongoose.disconnect();
}

