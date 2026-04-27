// Copyright (C) 2025-2026 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useNavigate, useLocation } from 'react-router-dom';
import { ThemeToggle } from './ThemeToggle';

const tabs = [
  { path: '/users', label: 'Users', icon: 'bi-people' },
  { path: '/groups', label: 'Groups', icon: 'bi-collection' },
  { path: '/dashboard', label: 'Dashboard', icon: 'bi-bar-chart-line' },
];

export function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const jhdata = (window as { jhdata?: { base_url?: string } }).jhdata ?? {};
  const baseUrl = jhdata.base_url ?? '/hub/';

  return (
    <div className="admin-header">
      <div className="admin-breadcrumb">
        <a href={`${baseUrl}home`}>Home</a>
        <span>›</span>
        <span>Administration</span>
      </div>
      <h1>Administration <ThemeToggle /></h1>
      <nav className="admin-nav">
        {tabs.map((tab) => (
          <button
            key={tab.path}
            className={`admin-nav-item${location.pathname === tab.path ? ' active' : ''}`}
            onClick={() => navigate(tab.path)}
          >
            <i className={`bi ${tab.icon}`} />
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
