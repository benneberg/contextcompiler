/**
 * Express server application.
 */
import express, { Request, Response } from "express";
import { User, CreateUserRequest, Platform, ApiResponse } from "./types";

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;

/**
 * Root endpoint.
 */
app.get("/", (req: Request, res: Response) => {
  res.json({ message: "Hello World" });
});

/**
 * Get user by ID.
 */
app.get("/api/users/:userId", (req: Request, res: Response<ApiResponse<User>>) => {
  const userId = parseInt(req.params.userId);
  
  const user: User = {
    id: userId,
    username: "testuser",
    email: "test@example.com",
    platform: Platform.ANDROID,
  };
  
  res.json({ data: user, status: "success" });
});

/**
 * Create a new user.
 */
app.post("/api/users", (req: Request<{}, {}, CreateUserRequest>, res: Response<ApiResponse<User>>) => {
  const { username, email, platform } = req.body;
  
  const user: User = {
    id: 1,
    username,
    email,
    platform,
  };
  
  res.json({ data: user, status: "created" });
});

/**
 * Delete a user.
 */
app.delete("/api/users/:userId", (req: Request, res: Response) => {
  const userId = parseInt(req.params.userId);
  res.json({ status: "deleted", userId });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

export default app;
