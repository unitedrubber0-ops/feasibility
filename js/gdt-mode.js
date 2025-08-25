// GD&T Mode Implementation
document.addEventListener('DOMContentLoaded', function() {
    // Initialize GD&T mode variables
    let isGdtMode = false;
    const modeToggle = document.getElementById('modeToggle');
    const gdtResultsContainer = document.getElementById('gdtResultsContainer');
    const gdtResultsBody = document.getElementById('gdtResultsBody');
    const cropSize = { width: 200, height: 50 }; // Size of the crop area

    // Mode toggle handler
    modeToggle?.addEventListener('click', () => {
        isGdtMode = !isGdtMode;
        modeToggle.textContent = isGdtMode ? 'GD&T Analysis Mode' : 'Ballooning Mode';
        modeToggle.classList.toggle('gdt-mode', isGdtMode);
        gdtResultsContainer?.classList.toggle('hidden', !isGdtMode);
    });

    // Function to crop the image around a click
    async function cropImageAtClick(canvas, x, y) {
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = cropSize.width;
        tempCanvas.height = cropSize.height;
        const ctx = tempCanvas.getContext('2d');
        
        // Calculate crop coordinates (centered on click)
        const sourceX = Math.max(0, x - cropSize.width / 2);
        const sourceY = Math.max(0, y - cropSize.height / 2);
        
        // Draw the cropped portion
        ctx.drawImage(canvas,
            sourceX, sourceY, cropSize.width, cropSize.height,
            0, 0, cropSize.width, cropSize.height
        );
        
        // Convert to blob
        return new Promise(resolve => {
            tempCanvas.toBlob(resolve, 'image/png');
        });
    }

    // Function to send cropped image to backend
    async function analyzeGdtCrop(imageBlob) {
        const formData = new FormData();
        formData.append('image_crop', imageBlob);
        
        try {
            const response = await fetch('http://localhost:5000/analyze-gdt-crop', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            displayGdtResults(data);
        } catch (error) {
            console.error('Error analyzing GD&T crop:', error);
            alert('Error analyzing GD&T feature. Please try again.');
        }
    }

    // Function to display GD&T results in the table
    function displayGdtResults(data) {
        if (!gdtResultsBody) return;
        
        const row = document.createElement('tr');
        
        // Format datums string
        const datumsStr = data.datums
            .map(d => `${d.datum_letter}${d.datum_material_condition ? ' ' + d.datum_material_condition : ''}`)
            .join(' | ');
        
        // Create cells
        row.innerHTML = `
            <td>${data.gdt_symbol_name}</td>
            <td>${data.diameter_symbol ? 'Ø' : ''}${data.tolerance_value}</td>
            <td>${datumsStr}</td>
            <td>${data.material_condition_modifier || '-'}</td>
        `;
        
        // Add to table
        gdtResultsBody.appendChild(row);
    }

    // Add click handler to viewer
    const viewer = document.getElementById('viewer');
    viewer?.addEventListener('click', async function(event) {
        if (!window.currentPage) return;
        
        const canvas = event.target;
        if (!(canvas instanceof HTMLCanvasElement)) return;
        
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        if (isGdtMode) {
            // GD&T Analysis Mode
            const imageBlob = await cropImageAtClick(canvas, x, y);
            await analyzeGdtCrop(imageBlob);
            
            // Show highlight box
            const highlight = document.createElement('div');
            highlight.className = 'gdt-highlight';
            highlight.style.left = (x - cropSize.width / 2) + 'px';
            highlight.style.top = (y - cropSize.height / 2) + 'px';
            highlight.style.width = cropSize.width + 'px';
            highlight.style.height = cropSize.height + 'px';
            viewer.appendChild(highlight);
            
            // Remove highlight after animation
            setTimeout(() => highlight.remove(), 2000);
        } else if (window.addBalloon) {
            // Original ballooning mode code
            window.addBalloon(x / canvas.width, y / canvas.height);
        }
    });
});
