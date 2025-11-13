// Optional Node-side helper if you later fetch weather directly from Node.
// For now, this provides a stub and a shape you can swap out.

export async function stubDailyForecast(days = 3) {
  return Array.from({ length: days }, (_, i) => ({
    date_index: i,
    avg_temp_c: 22 + i,
    avg_pop: 0.2,
    condition: "Clouds",
  }));
}
