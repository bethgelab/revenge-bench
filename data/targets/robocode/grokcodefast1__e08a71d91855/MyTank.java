package custom;
import java.util.ArrayList;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.BulletHitEvent;
import robocode.BulletMissedEvent;
import java.awt.*;

public class MyTank extends Robot {
    private ArrayList<Double> velocityHistory = new ArrayList<>();
    private ArrayList<Double> turnRateHistory = new ArrayList<>();
    private double lastEnemyHeading = 0;
    private double smoothedTurnRate = 0;
    private double smoothedVelocity = 0;
    private int hits = 0;
    private int misses = 0;

    public void run() {
        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.orange);
        setBulletColor(Color.cyan);
        setScanColor(Color.cyan);
        double width = getBattleFieldWidth();
        double height = getBattleFieldHeight();
        while(true) {
            if (getX() < 50 || getX() > width - 50 || getY() < 50 || getY() > height - 50) {
                double centerX = width / 2;
                double centerY = height / 2;
                double angleToCenter = Math.toDegrees(Math.atan2(centerX - getX(), centerY - getY()));
                turnRight(angleToCenter - getHeading());
                ahead(100);
            }
            boolean shouldMove = Math.random() < 0.9; // 90% chance to move
            if (shouldMove) {
                double turnAmount = Math.random() * 180 - 90; // Random turn -90 to 90
                turnRight(turnAmount);
                double moveDistance = Math.random() * 200 + 100; // Random ahead 100-300
                ahead(moveDistance);
            }
            turnRadarRight(360); // Continuous scanning
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        double distance = e.getDistance();
        double basePower = 400 / distance;
        if (basePower > 3) basePower = 3;
        double hitRate = (hits + misses) == 0 ? 0.5 : (double) hits / (hits + misses);
        if (hitRate < 0.3) basePower *= 1.2;
        else if (hitRate > 0.7) basePower *= 0.8;
        if (basePower > 3) basePower = 3;
        if (basePower < 0.1) basePower = 0.1;
        double power = basePower;
        if (getEnergy() < 10) power = 0; // Energy management: don't fire if low energy

        // Update velocity smoothing
        velocityHistory.add(e.getVelocity());
        if (velocityHistory.size() > 5) velocityHistory.remove(0);
        smoothedVelocity = velocityHistory.stream().mapToDouble(d -> d).average().orElse(e.getVelocity());
        double currentHeading = getHeading() + e.getBearing();
        double turnRate = currentHeading - lastEnemyHeading;
        turnRateHistory.add(turnRate);
        if (turnRateHistory.size() > 5) turnRateHistory.remove(0);
        smoothedTurnRate = turnRateHistory.stream().mapToDouble(d -> d).average().orElse(0);
        lastEnemyHeading = currentHeading;

        // Dynamic targeting: linear if turn rate low, circular otherwise
        double bulletSpeed = 20 - 3 * power;
        double predictedBearing;
        if (Math.abs(smoothedTurnRate) < 1) {
            predictedBearing = predictBearingLinear(e, distance, bulletSpeed);
        } else {
            predictedBearing = predictBearingCircular(e, distance, bulletSpeed);
        }

        turnGunRight(predictedBearing);
        if (power > 0) fire(power);
        if (distance < 100) back(100); // Anti-ramming
    }

    private double predictBearingCircular(ScannedRobotEvent e, double distance, double bulletSpeed) {
        double enemyHeading = getHeading() + e.getBearing();
        double enemyX = getX() + Math.sin(Math.toRadians(enemyHeading)) * distance;
        double enemyY = getY() + Math.cos(Math.toRadians(enemyHeading)) * distance;
        int ticks = (int) Math.ceil(distance / bulletSpeed);
        int maxTicks = 100; // Cap to prevent excessive computation
        if (ticks > maxTicks) ticks = maxTicks;
        for(int i = 0; i < ticks; i++){
            enemyX += Math.sin(Math.toRadians(enemyHeading)) * smoothedVelocity;
            enemyY += Math.cos(Math.toRadians(enemyHeading)) * smoothedVelocity;
            enemyHeading += smoothedTurnRate;
        }
        double bearingToPredicted = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY())) - getGunHeading();
        return bearingToPredicted;
    }

    private double predictBearingLinear(ScannedRobotEvent e, double distance, double bulletSpeed) {
        double enemyHeading = getHeading() + e.getBearing();
        double enemyX = getX() + Math.sin(Math.toRadians(enemyHeading)) * distance;
        double enemyY = getY() + Math.cos(Math.toRadians(enemyHeading)) * distance;
        int ticks = (int) Math.ceil(distance / bulletSpeed);
        int maxTicks = 100;
        if (ticks > maxTicks) ticks = maxTicks;
        for(int i = 0; i < ticks; i++){
            enemyX += Math.sin(Math.toRadians(enemyHeading)) * smoothedVelocity;
            enemyY += Math.cos(Math.toRadians(enemyHeading)) * smoothedVelocity;
            // enemyHeading stays the same for linear
        }
        double bearingToPredicted = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY())) - getGunHeading();
        return bearingToPredicted;
    }

    public void onBulletHit(BulletHitEvent e) {
        hits++;
    }

    public void onBulletMissed(BulletMissedEvent e) {
        misses++;
    }
}