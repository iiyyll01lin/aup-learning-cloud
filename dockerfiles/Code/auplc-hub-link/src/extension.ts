// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

import * as vscode from "vscode";

const COMMAND_ID = "auplc.backToHub";
const STATUS_BAR_TEXT = "$(home) JupyterHub";
const RUNTIME_STATUS_BAR_TEXT_PREFIX = "$(clock) Runtime:";
const RUNTIME_STATUS_BAR_UPDATE_INTERVAL_MS = 1000;

export interface RuntimeMetadata {
  startTimeSeconds: number;
  runTimeMinutes: number;
}

function getHubUrl(): string {
  return process.env.AUPLC_HUB_URL?.trim() || "/hub/home";
}

function getAbsoluteHttpUri(url: string): vscode.Uri | undefined {
  let parsedUrl: URL;

  try {
    parsedUrl = new URL(url);
  } catch {
    return undefined;
  }

  if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:") {
    return undefined;
  }

  return vscode.Uri.parse(parsedUrl.toString(), true);
}

function getInvalidHubUrlMessage(url: string): string {
  if (url.startsWith("/")) {
    return `AUPLC_HUB_URL is set to the relative path "${url}". Configure an absolute http(s) URL to enable the Back-to-Hub shortcut.`;
  }

  return `AUPLC_HUB_URL must be an absolute http(s) URL to enable the Back-to-Hub shortcut. Current value: "${url}".`;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function parseFiniteNumber(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }

  const parsedValue = Number(value.trim());
  return Number.isFinite(parsedValue) ? parsedValue : undefined;
}

export function getRuntimeMetadata(env: NodeJS.ProcessEnv = process.env): RuntimeMetadata | undefined {
  const startTimeSeconds = parseFiniteNumber(env.JOB_START_TIME);
  const runTimeMinutes = parseFiniteNumber(env.JOB_RUN_TIME);

  if (startTimeSeconds === undefined || startTimeSeconds <= 0 || runTimeMinutes === undefined || runTimeMinutes <= 0) {
    return undefined;
  }

  return {
    startTimeSeconds,
    runTimeMinutes,
  };
}

export function calculateRuntimeRemainingSeconds(metadata: RuntimeMetadata, nowSeconds: number): number {
  const totalSeconds = metadata.runTimeMinutes * 60;
  const elapsedSeconds = nowSeconds - metadata.startTimeSeconds;
  return Math.max(0, Math.floor(totalSeconds - elapsedSeconds));
}

export function formatRuntimeRemaining(remainingSeconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(remainingSeconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

export function getRuntimeStatusBarText(metadata: RuntimeMetadata, now: number = Date.now()): string {
  const nowSeconds = Math.floor(now / 1000);
  const remainingSeconds = calculateRuntimeRemainingSeconds(metadata, nowSeconds);
  return `${RUNTIME_STATUS_BAR_TEXT_PREFIX} ${formatRuntimeRemaining(remainingSeconds)}`;
}

async function openHub(): Promise<void> {
  const hubUrl = getHubUrl();
  const hubUri = getAbsoluteHttpUri(hubUrl);

  if (!hubUri) {
    await vscode.window.showWarningMessage(getInvalidHubUrlMessage(hubUrl));
    return;
  }

  await vscode.env.openExternal(hubUri);
}

function handleOpenHubError(error: unknown): void {
  void vscode.window.showErrorMessage(`Unable to open JupyterHub: ${getErrorMessage(error)}`);
}

function createRuntimeStatusBarItem(context: vscode.ExtensionContext): void {
  const metadata = getRuntimeMetadata();
  if (!metadata) {
    return;
  }

  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  const updateStatusBarItem = () => {
    statusBarItem.text = getRuntimeStatusBarText(metadata);
  };

  updateStatusBarItem();
  statusBarItem.tooltip = "Current server runtime remaining";
  statusBarItem.show();

  const interval = setInterval(updateStatusBarItem, RUNTIME_STATUS_BAR_UPDATE_INTERVAL_MS);
  const intervalDisposable = new vscode.Disposable(() => clearInterval(interval));

  context.subscriptions.push(statusBarItem, intervalDisposable);
}

export function activate(context: vscode.ExtensionContext): void {
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = STATUS_BAR_TEXT;
  statusBarItem.command = COMMAND_ID;
  statusBarItem.tooltip = "Back to JupyterHub";
  statusBarItem.show();

  const command = vscode.commands.registerCommand(COMMAND_ID, () => {
    void openHub().catch(handleOpenHubError);
  });

  context.subscriptions.push(statusBarItem, command);
  createRuntimeStatusBarItem(context);
}

export function deactivate(): void {}
