package custom;

import robocode.*;
import robocode.util.Utils;

import java.awt.*;
import java.awt.geom.Point2D;

public class MyTank extends AdvancedRobot {

    private double moveDirection = 1;
    private String targetName = null;
    private double targetDistance = Double.POSITIVE_INFINITY;
    private double lastEnemyEnergy = 100.0;
    private long lastDirChangeTime = 0;

    // New: tracking for improved targeting and radar recovery
    private double lastEnemyHeadingRad = Double.NaN;
    private long lastScanTime = -1;
    private int radarSweepDir = 1;

    @Override
    public void run() {
        setColors(new Color(20, 20, 20), new Color(200, 40, 40), new Color(240, 200, 40));
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        // Start sweeping radar indefinitely
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);

        double margin = 60;

        while (true) {
            // Simple lost-lock recovery: if we haven't scanned our target in a while, do a wide sweep
            if (targetName != null && lastScanTime >= 0 && getTime() - lastScanTime > 18) {
                radarSweepDir = -radarSweepDir;
                setTurnRadarRightRadians(radarSweepDir * Math.PI * 4);
            } else if (targetName == null) {
                // keep sweeping if no target
                setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
            }

            // Basic wall-awareness steering toward center if we get too close to walls
            double x = getX(), y = getY();
            double bfW = getBattleFieldWidth(), bfH = getBattleFieldHeight();

            if (x < margin || x > bfW - margin || y < margin || y > bfH - margin) {
                double angleToCenter = absoluteBearing(x, y, bfW / 2.0, bfH / 2.0);
                setTurnRight(normalizeBearing(angleToCenter - getHeading()));
                setAhead(140 * moveDirection);
            } else {
                // Default strafe forward; refined strafe happens in onScannedRobot when we have a target
                setAhead(160 * moveDirection);
            }

            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        // Target management with hysteresis: prefer current target; switch only if much closer
        if (targetName == null) {
            targetName = e.getName();
            targetDistance = e.getDistance();
            lastEnemyEnergy = e.getEnergy();
            lastEnemyHeadingRad = Math.toRadians(e.getHeading());
        } else if (targetName.equals(e.getName())) {
            targetDistance = e.getDistance();
        } else if (e.getDistance() + 40 < targetDistance) {
            // Switch if new bot is significantly closer
            targetName = e.getName();
            targetDistance = e.getDistance();
            lastEnemyEnergy = e.getEnergy();
            lastEnemyHeadingRad = Math.toRadians(e.getHeading());
        }

        // Track last scan time
        lastScanTime = getTime();

        // Compute absolute bearing to scanned bot
        double absBearingRad = Math.toRadians(getHeading() + e.getBearing());

        // Radar: only hard-lock when scanning our target; otherwise let the initial infinite sweep continue
        if (targetName != null && targetName.equals(e.getName())) {
            double radarTurn = Utils.normalRelativeAngle(absBearingRad - Math.toRadians(getRadarHeading()));
            // Lock with narrow double-turn to reduce slip
            setTurnRadarRightRadians(radarTurn * 2);
        }

        // Only aim/move/fire based on the current target
        if (targetName != null && targetName.equals(e.getName())) {
            // Movement: strafe perpendicular with slight jitter and periodic flips
            double jitter = Math.sin(getTime() / 12.0) * 10.0; // +/-10 degrees jitter
            double strafeTurn = e.getBearing() + 90.0 - ((12.0 + jitter) * moveDirection);
            setTurnRight(normalizeBearing(strafeTurn));

            // Distance-aware ahead distance to modulate orbit size
            double aheadDist = Math.min(220.0, (e.getDistance() / 2.0) + 100.0);
            setAhead(aheadDist * moveDirection);

            // Detect enemy fire by energy drop and flip with small cooldown
            double energyDrop = lastEnemyEnergy - e.getEnergy();
            if (energyDrop > 0.0 && energyDrop <= 3.0 && getTime() > lastDirChangeTime + 6) {
                moveDirection *= -1;
                lastDirChangeTime = getTime();
            }

            // Periodic direction change or if too close
            if (e.getDistance() < 140 || getTime() % 25 == 0) {
                if (getTime() > lastDirChangeTime + 5) {
                    moveDirection *= -1;
                    lastDirChangeTime = getTime();
                }
            }

            // Update tracked enemy energy
            lastEnemyEnergy = e.getEnergy();

            // Adaptive firepower based on distance and remaining energy
            double power = Math.min(3.0, Math.max(0.15, 350.0 / Math.max(50.0, e.getDistance())));
            if (getEnergy() < 15) {
                power = Math.min(power, 1.3);
            }
            if (getEnergy() < 5) {
                power = 0.2; // conserve when low
            }

            // Targeting with conditional circular prediction
            double bulletPower = power;
            double bulletSpeed = 20 - 3 * bulletPower;

            double myX = getX(), myY = getY();
            double enemyX = myX + e.getDistance() * Math.sin(absBearingRad);
            double enemyY = myY + e.getDistance() * Math.cos(absBearingRad);

            double enemyHeadingRad = Math.toRadians(e.getHeading());
            double enemyVelocity = e.getVelocity();

            double enemyHeadingChange = 0.0;
            if (!Double.isNaN(lastEnemyHeadingRad)) {
                enemyHeadingChange = Utils.normalRelativeAngle(enemyHeadingRad - lastEnemyHeadingRad);
            }
            lastEnemyHeadingRad = enemyHeadingRad;

            // Lateral velocity magnitude to decide targeting mode
            double lateralVelocity = e.getVelocity() * Math.sin(enemyHeadingRad - absBearingRad);
            boolean useCircular = Math.abs(enemyHeadingChange) > 0.02 || Math.abs(lateralVelocity) > 4.0;

            // Predict enemy position where bullet will intersect
            double bfW = getBattleFieldWidth(), bfH = getBattleFieldHeight();
            double predictedX = enemyX, predictedY = enemyY;
            double time = 0;

            if (useCircular) {
                // Constant turn-rate, constant speed circular prediction
                double ph = enemyHeadingRad;
                double pv = enemyVelocity;
                while ((++time) * bulletSpeed < Point2D.distance(myX, myY, predictedX, predictedY)) {
                    ph = Utils.normalRelativeAngle(ph + enemyHeadingChange);
                    predictedX += Math.sin(ph) * pv;
                    predictedY += Math.cos(ph) * pv;

                    // Stop prediction at battlefield edges
                    if (predictedX < 18 || predictedY < 18 || predictedX > bfW - 18 || predictedY > bfH - 18) {
                        predictedX = Math.min(Math.max(18, predictedX), bfW - 18);
                        predictedY = Math.min(Math.max(18, predictedY), bfH - 18);
                        break;
                    }
                }
            } else {
                // Linear prediction (fallback / low-turn-rate)
                while ((++time) * bulletSpeed < Point2D.distance(myX, myY, predictedX, predictedY)) {
                    predictedX += Math.sin(enemyHeadingRad) * enemyVelocity;
                    predictedY += Math.cos(enemyHeadingRad) * enemyVelocity;

                    // Stop prediction at battlefield edges
                    if (predictedX < 18 || predictedY < 18 || predictedX > bfW - 18 || predictedY > bfH - 18) {
                        predictedX = Math.min(Math.max(18, predictedX), bfW - 18);
                        predictedY = Math.min(Math.max(18, predictedY), bfH - 18);
                        break;
                    }
                }
            }

            double gunTurnRad = Utils.normalRelativeAngle(
                    Math.atan2(predictedX - myX, predictedY - myY) - Math.toRadians(getGunHeading())
            );

            setTurnGunRightRadians(gunTurnRad);

            // Dynamic aim tolerance: stricter at range, looser up close
            double aimTolRad = Math.toRadians(Math.min(12.0, Math.max(2.0, 450.0 / (e.getDistance() + 50.0))));

            // Only fire when we are reasonably aimed and gun is ready
            if (getGunHeat() == 0 && Math.abs(gunTurnRad) < aimTolRad) {
                setFire(bulletPower);
            }
        }
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        // Change direction when hit to be less predictable
        moveDirection *= -1;
        lastDirChangeTime = getTime();
        setAhead(140 * moveDirection);
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        // Bounce off the wall
        moveDirection *= -1;
        lastDirChangeTime = getTime();
        setBack(140);
    }

    @Override
    public void onRobotDeath(RobotDeathEvent e) {
        if (targetName != null && targetName.equals(e.getName())) {
            targetName = null;
            targetDistance = Double.POSITIVE_INFINITY;
            lastEnemyEnergy = 100.0;
            lastEnemyHeadingRad = Double.NaN;
            lastScanTime = -1;
        }
    }

    // Utilities

    private static double normalizeBearing(double angleDeg) {
        double a = angleDeg;
        while (a > 180) a -= 360;
        while (a < -180) a += 360;
        return a;
    }

    private static double absoluteBearing(double x1, double y1, double x2, double y2) {
        // Robocode 0 degrees is up; atan2(dx, dy) aligns with that
        return Math.toDegrees(Math.atan2(x2 - x1, y2 - y1));
    }
}