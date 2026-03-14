/**
 * Type definitions for the application.
 */

export enum Platform {
  ANDROID = "android",
  IOS = "ios",
  WEB = "web",
}

export interface User {
  id: number;
  username: string;
  email: string;
  platform: Platform;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  platform: Platform;
}

export interface ApiResponse<T> {
  data: T;
  status: string;
}
