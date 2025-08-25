// GD&T Mode Implementation
const GdtAnalyzer = {
    cropSize: { width: 200, height: 50 }, // Size of the crop area

    // Function to crop the image around a click
    async cropImageAtClick(canvas, x, y) {
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = this.cropSize.width;
        tempCanvas.height = this.cropSize.height;
        const ctx = tempCanvas.getContext('2d');
        
        // Calculate crop coordinates (centered on click)
        const sourceX = Math.max(0, x - this.cropSize.width / 2);
        const sourceY = Math.max(0, y - this.cropSize.height / 2);
        
        // Draw the cropped portion
        ctx.drawImage(canvas,
            sourceX, sourceY, this.cropSize.width, this.cropSize.height,
            0, 0, this.cropSize.width, this.cropSize.height
        );
        
        // Convert to blob
        return new Promise(resolve => {
            tempCanvas.toBlob(resolve, 'image/png');
        });
    },

    // Function to send cropped image to backend
    async analyzeGdtCrop(imageBlob, backendUrl) {
        if (!backendUrl) {
            throw new Error('Backend URL not provided');
        }

        const formData = new FormData();
        formData.append('image_crop', imageBlob);
        
        const response = await fetch(`${backendUrl}/analyze-gdt-crop`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    },

    // Function to display results in the GD&T table
    displayResults(data, gdtResultsBody) {
        if (!gdtResultsBody) {
            console.error('GD&T results table body not found');
            return;
        }
        
        gdtResultsBody.innerHTML = ''; // Clear previous results
        
        if (data.features && Array.isArray(data.features)) {
            data.features.forEach(feature => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${feature.characteristic || 'Unknown'}</td>
                    <td>${feature.value || 'N/A'}</td>
                    <td>${feature.datums?.join(', ') || 'None'}</td>
                    <td>${feature.modifiers?.join(', ') || 'None'}</td>
                `;
                gdtResultsBody.appendChild(tr);
            });
        } else {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="4">No GD&T features detected in this area</td>';
            gdtResultsBody.appendChild(tr);
        }
    }
};

// Export the GdtAnalyzer object
window.GdtAnalyzer = GdtAnalyzer;
