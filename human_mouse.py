import math
import random
from dataclasses import dataclass

import numpy as np
from scipy import interpolate

@dataclass(frozen=True)
class MouseConfig:
    speed_factor: float = 0.5
    zigzag_probability: float = 0.75
    min_nodes: int = 2
    max_nodes: int = 15
    variance_factor: float = 0.15
    max_variance: float = 100
    points_per_path: int = 100

class HumanMouse:
    def __init__(self, config: MouseConfig | None = None):
        self.config = config or MouseConfig()

    def generate_path(self, start_x: float, start_y: float, end_x: float, end_y: float) -> list[tuple[float, float]]:
        distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
        if distance < 1:
            return [(end_x, end_y)]

        num_nodes = random.randint(self.config.min_nodes, self.config.max_nodes)
        variance = min(distance * self.config.variance_factor, self.config.max_variance)

        if random.random() < self.config.zigzag_probability:
            control_points = self._generate_zigzag_points(start_x, start_y, end_x, end_y, num_nodes, variance)
        else:
            control_points = self._generate_curved_points(start_x, start_y, end_x, end_y, num_nodes, variance)
        return self._compute_spline_trajectory(control_points)

    def _generate_zigzag_points(self, start_x: float, start_y: float, end_x: float, end_y: float,
                                 num_nodes: int, variance: float) -> list[tuple[float, float]]:
        x_coords = np.linspace(start_x, end_x, num_nodes)
        y_coords = np.linspace(start_y, end_y, num_nodes)
        for i in range(1, num_nodes - 1):
            x_coords[i] += random.uniform(-variance, variance)
            y_coords[i] += random.uniform(-variance, variance)
        return list(zip(x_coords, y_coords))

    def _generate_curved_points(self, start_x: float, start_y: float, end_x: float, end_y: float,
                                 num_nodes: int, variance: float) -> list[tuple[float, float]]:
        x_coords = np.linspace(start_x, end_x, num_nodes)
        y_coords = np.linspace(start_y, end_y, num_nodes)
        offset_x = np.random.normal(0, variance * 0.5, num_nodes)
        offset_y = np.random.normal(0, variance * 0.5, num_nodes)
        offset_x[0] = offset_x[-1] = 0
        offset_y[0] = offset_y[-1] = 0
        return list(zip(x_coords + offset_x, y_coords + offset_y))

    def _compute_spline_trajectory(self, control_points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(control_points) < 2:
            return control_points

        x = np.array([p[0] for p in control_points])
        y = np.array([p[1] for p in control_points])

        if len(control_points) < 4:
            t = np.linspace(0, 1, self.config.points_per_path)
            return list(zip(np.interp(t, np.linspace(0, 1, len(x)), x),
                           np.interp(t, np.linspace(0, 1, len(y)), y)))
        try:
            k = min(3, len(x) - 1)
            tck, _ = interpolate.splprep([x, y], s=0, k=k)
            t = np.linspace(0, 1, self.config.points_per_path)
            smooth_x, smooth_y = interpolate.splev(t, tck)
            return list(zip(smooth_x, smooth_y))
        except Exception:
            t = np.linspace(0, 1, self.config.points_per_path)
            return list(zip(np.interp(t, np.linspace(0, 1, len(x)), x),
                           np.interp(t, np.linspace(0, 1, len(y)), y)))

    def calculate_delays(self, path: list[tuple[float, float]]) -> list[float]:
        if len(path) < 2:
            return [0]

        total_distance = sum(math.sqrt((path[i][0] - path[i-1][0])**2 + (path[i][1] - path[i-1][1])**2)
                            for i in range(1, len(path)))

        exponent = random.uniform(1.1, 1.75)
        adjustment = random.uniform(1.1, 1.75)
        base_duration = max(100, min(((total_distance ** exponent) / adjustment) * self.config.speed_factor, 2000))

        delays = []
        for i in range(1, len(path)):
            segment_dist = math.sqrt((path[i][0] - path[i-1][0])**2 + (path[i][1] - path[i-1][1])**2)
            proportion = segment_dist / total_distance if total_distance > 0 else 1 / len(path)
            delays.append(base_duration * proportion * random.uniform(0.8, 1.2))
        return delays
