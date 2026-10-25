(function () {
  const dataElement = document.getElementById("bill-data");
  if (!dataElement) return;
  const data = JSON.parse(dataElement.textContent);
  const days = data.days;
  const tariffSlabs = data.tariff_slabs;
  const dayPicker = document.getElementById("bill-day-date");

  function chargeFor(units) {
    const slabs = units <= 500
      ? tariffSlabs.up_to_500
      : tariffSlabs.above_500;
    let remaining = units;
    let charge = 0;
    for (const [slabUnits, rate] of slabs) {
      const billedUnits = Math.min(
        remaining,
        slabUnits == null ? remaining : slabUnits
      );
      charge += billedUnits * rate;
      remaining -= billedUnits;
      if (remaining <= 0) break;
    }
    return Math.round((charge + Number.EPSILON) * 100) / 100;
  }

  function slabDetails(units) {
    const slabs = units <= 500
      ? tariffSlabs.up_to_500
      : tariffSlabs.above_500;
    let lowerBound = 0;
    for (const [slabUnits, rate] of slabs) {
      const upperBound = slabUnits == null
        ? Infinity
        : lowerBound + slabUnits;
      if (units <= upperBound || !Number.isFinite(upperBound)) {
        const range = Number.isFinite(upperBound)
          ? `${lowerBound === 0 ? 0 : lowerBound + 1}–${upperBound} units`
          : `Above ${lowerBound} units`;
        return {
          label: range,
          rate: Number(rate),
        };
      }
      lowerBound = upperBound;
    }
    return { label: "", rate: 0 };
  }

  function updateEstimate() {
    const index = days.findIndex((day) => day.date === dayPicker.value);
    if (index < 0) return;
    const day = days[index];
    let cumulativeUnits = 0;
    for (let i = 0; i <= index; i += 1) cumulativeUnits += days[i].units;

    const cumulativeCharge = chargeFor(cumulativeUnits);
    const slab = slabDetails(cumulativeUnits);

    document.getElementById("selected-day").textContent = day.date;
    document.getElementById("usage-source").textContent =
      day.data_type === "predicted" ? "Predicted usage for a missing reading" :
      day.data_type === "estimated" ? "User-entered estimate" : "Measured usage";
    document.getElementById("day-units").textContent = `${day.units.toFixed(2)} kWh`;
    document.getElementById("cumulative-units").textContent =
      `${cumulativeUnits.toFixed(2)} kWh`;
    document.getElementById("day-charge").textContent = `₹${cumulativeCharge.toFixed(2)}`;
    document.getElementById("tariff-slab").textContent =
      slab.label;
    document.getElementById("tariff-rate").textContent =
      `₹${slab.rate.toFixed(2)} per unit`;
  }

  dayPicker.addEventListener("change", updateEstimate);
  updateEstimate();
})();
