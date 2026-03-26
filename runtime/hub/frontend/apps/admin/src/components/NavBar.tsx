// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { Nav } from 'react-bootstrap';
import { useNavigate, useLocation } from 'react-router-dom';

export function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Nav variant="tabs" className="mb-4">
      <Nav.Item>
        <Nav.Link
          active={location.pathname === '/users'}
          onClick={() => navigate('/users')}
        >
          <i className="bi bi-people me-1" />
          Users
        </Nav.Link>
      </Nav.Item>
      <Nav.Item>
        <Nav.Link
          active={location.pathname === '/groups'}
          onClick={() => navigate('/groups')}
        >
          <i className="bi bi-collection me-1" />
          Groups
        </Nav.Link>
      </Nav.Item>
      <Nav.Item>
        <Nav.Link
          active={location.pathname === '/dashboard'}
          onClick={() => navigate('/dashboard')}
        >
          <i className="bi bi-bar-chart-line me-1" />
          Dashboard
        </Nav.Link>
      </Nav.Item>
    </Nav>
  );
}
