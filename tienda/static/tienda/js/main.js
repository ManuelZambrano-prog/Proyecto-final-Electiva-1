/* ==========================================================================
   INTERACTIVIDAD Y SIMULADOR DE RIEGO INTELIGENTE
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initSimulator();
    initPlantCalculator();
    initCheckoutCalculator();
});

/* --------------------------------------------------------------------------
   1. SIMULADOR EN VIVO DEL SISTEMA DE RIEGO Y NOTIFICACIONES
   -------------------------------------------------------------------------- */
function initSimulator() {
    const humSlider = document.getElementById('sim-humidity');
    const tempSlider = document.getElementById('sim-temp');
    const humVal = document.getElementById('sim-hum-val');
    const tempVal = document.getElementById('sim-temp-val');
    const plantStatus = document.getElementById('sim-plant-status');
    const plantAvatar = document.getElementById('sim-plant-avatar');
    const notifBox = document.getElementById('sim-notification');
    const notifMsg = document.getElementById('sim-notif-msg');
    const btnWater = document.getElementById('sim-btn-water');
    const waterDispensed = document.getElementById('sim-water-dispensed');
    const monitorCard = document.getElementById('sim-monitor-card');

    if (!humSlider || !btnWater) return;

    let liters = 1.45;
    let isWatering = false;
    let waterInterval = null;

    function updateSensors() {
        const hum = parseInt(humSlider.value, 10);
        const temp = parseInt(tempSlider.value, 10);

        humVal.textContent = `${hum}%`;
        tempVal.textContent = `${temp}°C`;

        if (hum < 35) {
            plantStatus.textContent = '🥀 Suelo Seco (Requiere Riego)';
            plantStatus.style.color = 'var(--danger)';
            plantAvatar.textContent = '🥀';
            notifBox.style.display = 'flex';
            notifMsg.innerHTML = `<strong>⚠️ ALERTA:</strong> La humedad de tu <em>Monstera Deliciosa</em> cayó a <strong>${hum}%</strong> con temp. de <strong>${temp}°C</strong>. Se recomienda regar 250ml. ¿Deseas habilitar la electroválvula?`;
            btnWater.classList.remove('btn-secondary');
            btnWater.classList.add('btn-primary');
            btnWater.textContent = '💧 Habilitar Riego Ahora';
        } else if (hum > 75) {
            plantStatus.textContent = '💧 Suelo Muy Húmedo';
            plantStatus.style.color = 'var(--info)';
            plantAvatar.textContent = '🪴';
            notifBox.style.display = 'none';
        } else {
            plantStatus.textContent = '🌿 Nivel Óptimo y Saludable';
            plantStatus.style.color = 'var(--green-700)';
            plantAvatar.textContent = '🌿';
            notifBox.style.display = 'none';
        }
    }

    humSlider.addEventListener('input', updateSensors);
    tempSlider.addEventListener('input', updateSensors);

    btnWater.addEventListener('click', () => {
        if (isWatering) {
            // Detener riego manual
            stopWatering();
            return;
        }

        // Iniciar riego
        isWatering = true;
        monitorCard.classList.add('is-watering');
        btnWater.textContent = '⏹️ Detener Riego (Válvula Abierta)';
        btnWater.classList.remove('btn-primary');
        btnWater.classList.add('btn-accent');

        waterInterval = setInterval(() => {
            let currentHum = parseInt(humSlider.value, 10);
            if (currentHum < 70) {
                currentHum += 3;
                humSlider.value = currentHum;
                liters += 0.05;
                waterDispensed.textContent = `${liters.toFixed(2)} L`;
                updateSensors();
            } else {
                stopWatering();
            }
        }, 400);
    });

    function stopWatering() {
        isWatering = false;
        clearInterval(waterInterval);
        monitorCard.classList.remove('is-watering');
        btnWater.textContent = '✅ Riego Completado (+0.25 L)';
        btnWater.classList.remove('btn-accent');
        btnWater.classList.add('btn-secondary');
        setTimeout(() => {
            btnWater.textContent = '💧 Habilitar Riego Ahora';
            btnWater.classList.remove('btn-secondary');
            btnWater.classList.add('btn-primary');
        }, 2500);
    }

    // Inicializar valores al cargar
    updateSensors();
}

/* --------------------------------------------------------------------------
   2. CALCULADORA Y RECOMENDADOR DE KIT SEGÚN PLANTAS EN CASA
   -------------------------------------------------------------------------- */
function initPlantCalculator() {
    const calcSlider = document.getElementById('calc-plant-count');
    const calcCountDisplay = document.getElementById('calc-count-display');
    const recKitName = document.getElementById('rec-kit-name');
    const recKitDesc = document.getElementById('rec-kit-desc');
    const recKitPrice = document.getElementById('rec-kit-price');
    const recKitBtn = document.getElementById('rec-kit-btn');

    if (!calcSlider || !recKitName) return;

    function evaluateRecommendation() {
        const count = parseInt(calcSlider.value, 10);
        calcCountDisplay.textContent = count === 1 ? '1 Planta' : `${count} Plantas`;

        if (count <= 3) {
            recKitName.textContent = 'Kit Balcón & Ventana (1 - 3 plantas)';
            recKitDesc.textContent = 'Incluye 1 electroválvula, 5m de manguera y depósito compacto de 4L.';
            recKitPrice.textContent = '$99.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-balcon-ventana';
        } else if (count <= 8) {
            recKitName.textContent = 'Kit Hogar Verde Pro (4 - 8 plantas) ⭐ Recomendado';
            recKitDesc.textContent = 'Incluye 1 electroválvula, 12m de microtubo, tanque de 10L y sensores de humedad y temperatura.';
            recKitPrice.textContent = '$169.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-hogar-verde-pro';
        } else {
            recKitName.textContent = 'Kit Jardín Interior Smart (hasta 16 plantas)';
            recKitDesc.textContent = 'Incluye 1 electroválvula modular, 25m de tubería, tanque 20L o conector a grifo.';
            recKitPrice.textContent = '$259.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-jardin-interior-smart';
        }
    }

    calcSlider.addEventListener('input', evaluateRecommendation);
    evaluateRecommendation();
}

/* --------------------------------------------------------------------------
   3. CÁLCULO DINÁMICO EN CHECKOUT
   -------------------------------------------------------------------------- */
function initCheckoutCalculator() {
    const kitSelect = document.getElementById('id_kit');
    const chkTanque = document.getElementById('id_tanque_extra');
    const chkSensores = document.getElementById('id_sensores_extra');
    const totalDisplay = document.getElementById('summary-total-display');
    const kitNameDisplay = document.getElementById('summary-kit-name');
    const kitPriceDisplay = document.getElementById('summary-kit-price');
    const extraTanqueRow = document.getElementById('summary-extra-tanque');
    const extraSensoresRow = document.getElementById('summary-extra-sensores');

    if (!kitSelect || !totalDisplay) return;

    // Precios de kits (asociados por texto o valor)
    const preciosKits = {
        '1': { nombre: 'Kit Balcón & Ventana', precio: 99000 },
        '2': { nombre: 'Kit Hogar Verde Pro', precio: 169000 },
        '3': { nombre: 'Kit Jardín Interior Smart', precio: 259000 }
    };

    function recalculateTotal() {
        const kitId = kitSelect.value;
        const kitInfo = preciosKits[kitId] || { nombre: 'Kit Seleccionado', precio: 169000 };

        let total = kitInfo.precio;
        if (kitNameDisplay) kitNameDisplay.textContent = kitInfo.nombre;
        if (kitPriceDisplay) kitPriceDisplay.textContent = `$${kitInfo.precio.toLocaleString('es-CO')}`;

        if (chkTanque && chkTanque.checked) {
            total += 35000;
            if (extraTanqueRow) extraTanqueRow.style.display = 'flex';
        } else {
            if (extraTanqueRow) extraTanqueRow.style.display = 'none';
        }

        if (chkSensores && chkSensores.checked) {
            total += 28000;
            if (extraSensoresRow) extraSensoresRow.style.display = 'flex';
        } else {
            if (extraSensoresRow) extraSensoresRow.style.display = 'none';
        }

        totalDisplay.textContent = `$${total.toLocaleString('es-CO')}`;
    }

    kitSelect.addEventListener('change', recalculateTotal);
    if (chkTanque) chkTanque.addEventListener('change', recalculateTotal);
    if (chkSensores) chkSensores.addEventListener('change', recalculateTotal);

    recalculateTotal();
}
