import { Schema, model, type Document } from "mongoose";

export interface IProjectRecord extends Document {
  projectId: string;
  title: string;
  userInitialPrompt: string;
  currentPhase: string;
  currentVersion: number;
  activeCheckpoint: string | null;
  latestState: Record<string, unknown>;
  versions: Array<Record<string, unknown>>;
  createdAt: Date;
  updatedAt: Date;
}

const projectRecordSchema = new Schema<IProjectRecord>(
  {
    projectId: {
      type: String,
      required: true,
      unique: true,
      index: true,
    },
    title: {
      type: String,
      required: true,
      trim: true,
    },
    userInitialPrompt: {
      type: String,
      required: true,
      trim: true,
    },
    currentPhase: {
      type: String,
      required: true,
    },
    currentVersion: {
      type: Number,
      required: true,
      default: 1,
    },
    activeCheckpoint: {
      type: String,
      default: null,
    },
    latestState: {
      type: Schema.Types.Mixed,
      required: true,
    },
    versions: {
      type: [Schema.Types.Mixed] as any,
      default: [],
    },
  },
  {
    timestamps: true,
  }
);

export const ProjectRecord = model<IProjectRecord>("ProjectRecord", projectRecordSchema);

