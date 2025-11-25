// dashboard.js
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('vacationForm');
  const messageDisplay = document.getElementById('message');
  const tableBody = document.getElementById('requests-body');
  const statusFilter = document.getElementById('statusFilter');

  // ---------------------------
  // Load vacation requests with optional filter
  // ---------------------------
  async function loadRequests(filter = 'All') {
    if (!tableBody) return;

    tableBody.innerHTML = '<tr><td colspan="7" class="text-center">Loading requests...</td></tr>';

    try {
      const response = await fetch('/requests');
      if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

      let requests = await response.json();

      if (filter.toLowerCase() !== 'all') {
        requests = requests.filter(req => req.status.toLowerCase() === filter.toLowerCase());
      }

      tableBody.innerHTML = '';
      if (requests.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No vacation requests found.</td></tr>';
        return;
      }

      requests.forEach(req => addRow(req));

    } catch (error) {
      console.error('Error loading requests:', error);
      tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">⚠️ Cannot connect to server. ${error.message}</td></tr>`;
    }
  }

  // ---------------------------
  // Add a single row
  // ---------------------------
  function addRow(request) {
    const row = document.createElement('tr');

    let statusClass;
    switch (request.status) {
      case 'Approved': statusClass = 'text-success'; break;
      case 'Rejected': statusClass = 'text-danger'; break;
      default: statusClass = 'text-warning';
    }

    row.innerHTML = `
      <th scope="row">${request.id}</th>
      <td>${request.employee_name}</td>
      <td>${request.date_start}</td>
      <td>${request.date_end}</td>
      <td class="${statusClass} fw-bold">${request.status}</td>
      <td>${request.submitted_at ? request.submitted_at.split('T')[0] : ''}</td>
      <td>
        ${request.status === 'Pending' ? `
          <button class="btn btn-outline-success btn-sm btn-approve" title="Approve">✔️</button>
          <button class="btn btn-outline-danger btn-sm btn-reject" title="Reject">❌</button>` : ''}
        <button class="btn btn-outline-dark btn-sm btn-delete" title="Delete">🗑️</button>
      </td>
    `;

    tableBody.appendChild(row);

    // --- Delete button ---
    row.querySelector('.btn-delete')?.addEventListener('click', async () => {
      const confirmed = await showConfirmModal(`Delete request #${request.id}?`);
      if (!confirmed) return;

      try {
        const response = await fetch(`/delete/${request.id}`, { method: 'DELETE' });
        const result = await response.json();
        if (response.ok) {
          showInfoModal(`✅ ${result.message}`);
          row.remove();
        } else {
          showInfoModal(`❌ Error: ${result.error || 'Unable to delete request.'}`, 'Error');
        }
      } catch {
        showInfoModal('⚠️ Connection error with server.', 'Error');
      }
    });

    // --- Approve button ---
    row.querySelector('.btn-approve')?.addEventListener('click', async () => {
      const confirmed = await showConfirmModal(`Approve request #${request.id}?`);
      if (!confirmed) return;

      try {
        const response = await fetch(`/approve/${request.id}`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
          showInfoModal(`✅ ${result.message}`);
          updateRowStatus(row, 'Approved', 'text-success');
        } else {
          showInfoModal(`❌ Error: ${result.error || 'Unable to approve request.'}`, 'Error');
        }
      } catch {
        showInfoModal('⚠️ Connection error with server.', 'Error');
      }
    });

    // --- Reject button ---
    row.querySelector('.btn-reject')?.addEventListener('click', async () => {
      const confirmed = await showConfirmModal(`Reject request #${request.id}?`);
      if (!confirmed) return;

      try {
        const response = await fetch(`/reject/${request.id}`, { method: 'POST' });
        const result = await response.json();
        if (response.ok) {
          showInfoModal(`✅ ${result.message}`);
          updateRowStatus(row, 'Rejected', 'text-danger');
        } else {
          showInfoModal(`❌ Error: ${result.error || 'Unable to reject request.'}`, 'Error');
        }
      } catch {
        showInfoModal('⚠️ Connection error with server.', 'Error');
      }
    });
  }

  // ---------------------------
  // Modals
  // ---------------------------

  // Confirmation modal (Confirm/Cancel)
  function showConfirmModal(message) {
    return new Promise((resolve) => {
      const modalEl = document.getElementById('confirmModal');
      const messageEl = document.getElementById('confirmModalMessage');
      const confirmBtn = document.getElementById('confirmModalConfirmBtn');

      messageEl.textContent = message;

      const modal = new bootstrap.Modal(modalEl);
      modal.show();

      const onConfirm = () => {
        resolve(true);
        confirmBtn.removeEventListener('click', onConfirm);
        modal.hide();
      };

      modalEl.addEventListener('hidden.bs.modal', () => {
        confirmBtn.removeEventListener('click', onConfirm);
        resolve(false);
      }, { once: true });

      confirmBtn.addEventListener('click', onConfirm);
    });
  }

  // Info modal (simple "Done" message)
  function showInfoModal(message, title = 'Done') {
    const modalEl = document.getElementById('infoModal');
    const messageEl = document.getElementById('infoModalMessage');
    const titleEl = document.getElementById('infoModalLabel');

    messageEl.textContent = message;
    titleEl.textContent = title;

    const modal = new bootstrap.Modal(modalEl);
    modal.show();

    // Auto-close after 2.5 seconds
    setTimeout(() => modal.hide(), 2500);
  }

  // ---------------------------
  // Update row status dynamically
  // ---------------------------
  function updateRowStatus(row, statusText, statusClass) {
    const statusCell = row.querySelector('td:nth-child(5)');
    statusCell.textContent = statusText;
    statusCell.className = `${statusClass} fw-bold`;
    row.querySelector('.btn-approve')?.remove();
    row.querySelector('.btn-reject')?.remove();
  }

  // ---------------------------
  // Handle new vacation form submission
  // ---------------------------
  if (form && messageDisplay) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      messageDisplay.style.display = 'block';
      messageDisplay.textContent = 'Submitting...';
      messageDisplay.className = 'alert alert-info mt-3';

      const data = {
        name: document.getElementById('nombre').value,
        date_start: document.getElementById('date_start').value,
        date_end: document.getElementById('date_end').value
      };

      try {
        const response = await fetch('/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
          messageDisplay.textContent = `✅ Success: ${result.message} (ID: ${result.id})`;
          messageDisplay.className = 'alert alert-success mt-3';
          form.reset();

          // Add new row if filter allows
          if (!statusFilter || statusFilter.value === 'All' || statusFilter.value === 'Pending') {
            addRow({
              id: result.id,
              employee_name: data.name,
              date_start: data.date_start,
              date_end: data.date_end,
              status: 'Pending',
              submitted_at: new Date().toISOString()
            });
          }

        } else {
          messageDisplay.textContent = `❌ Error: ${result.error || 'An unknown error occurred.'}`;
          messageDisplay.className = 'alert alert-danger mt-3';
        }
      } catch (error) {
        console.error('Network error:', error);
        messageDisplay.textContent = '❌ Connection error: Make sure the Flask server is running.';
        messageDisplay.className = 'alert alert-danger mt-3';
      }
    });
  }

  // ---------------------------
  // Filter by status dynamically
  // ---------------------------
  statusFilter?.addEventListener('change', () => loadRequests(statusFilter.value));

  // ---------------------------
  // Initial load
  // ---------------------------
  loadRequests();
});
