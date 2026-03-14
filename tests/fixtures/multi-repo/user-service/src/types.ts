/**
 * User Service Types
 * 
 * NOTE: Some types intentionally conflict with auth-service for testing
 */

// This enum has different values than auth-service (intentional conflict)
export enum UserRole {
  ADMIN = "admin",
  USER = "user",
  MODERATOR = "moderator",  // Not in auth-service
}

// Same as auth-service
export interface UserProfile {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  createdAt: Date;
}

// Different fields than auth-service User (intentional conflict)
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  // Missing: passwordHash, createdAt
}

// Constant with different value (intentional conflict)
export const API_VERSION = "v2";  // auth-service has "v1"
export const MAX_CONNECTIONS = 100;
