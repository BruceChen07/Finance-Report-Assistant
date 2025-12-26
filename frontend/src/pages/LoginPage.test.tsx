import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const loginMock = vi.fn();
const setLoadingMock = vi.fn();
const toastMock = vi.fn();

vi.mock("../components/providers/AuthProvider", () => {
  return {
    useAuth: () => ({
      token: null,
      username: null,
      login: loginMock,
      logout: vi.fn()
    })
  };
});

vi.mock("../components/providers/UiProvider", () => {
  return {
    useUi: () => ({
      loading: false,
      setLoading: setLoadingMock,
      toast: toastMock
    })
  };
});

import LoginPage from "./LoginPage";

beforeEach(() => {
  loginMock.mockReset();
  setLoadingMock.mockReset();
  toastMock.mockReset();
});

describe("LoginPage", () => {
  it("calls login and shows an error toast on failure", async () => {
    loginMock.mockRejectedValueOnce(new Error("bad"));

    render(<LoginPage />);

    fireEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => expect(loginMock).toHaveBeenCalledWith("admin", "admin"));
    await waitFor(() => expect(toastMock).toHaveBeenCalledWith("Login failed: bad", "error"));
    expect(setLoadingMock).toHaveBeenCalledWith(true);
    expect(setLoadingMock).toHaveBeenLastCalledWith(false);
  });
});