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

function getHubUrl(): string {
  return process.env.AUPLC_HUB_URL || "/hub/home";
}

async function openHub(): Promise<void> {
  await vscode.env.openExternal(vscode.Uri.parse(getHubUrl(), true));
}

export function activate(context: vscode.ExtensionContext): void {
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = STATUS_BAR_TEXT;
  statusBarItem.command = COMMAND_ID;
  statusBarItem.tooltip = "Back to JupyterHub";
  statusBarItem.show();

  const command = vscode.commands.registerCommand(COMMAND_ID, () => {
    void openHub();
  });

  context.subscriptions.push(statusBarItem, command);
}

export function deactivate(): void {}
