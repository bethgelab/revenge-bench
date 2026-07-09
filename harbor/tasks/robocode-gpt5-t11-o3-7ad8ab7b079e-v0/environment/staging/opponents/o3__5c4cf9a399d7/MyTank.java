package custom;

import robocode.*;
import robocode.util.Utils;

import java.awt.*;
import java.awt.geom.Point2D;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

/**
 * MyTank â Round 9
 *
 * Improvements this round:
 *  â¢ Switched singleâvalue enemy energy/heading tracking to perâenemy HashMaps.
 *    This fixes incorrect energyâdrop detection and headingâchange estimation
 *    when fighting multiple opponents (1-vs-many and melee battles).
 *  â¢ Code clean-up: removed obsolete fields, inlined constants.
 *
 *  Existing features retained:
 *  â¢ Perpendicular strafe movement with random reversals and dodge on bullet hit.
 *  â¢ Detect enemy energy drop (shot fired) and dodge.
 *  â¢ Linear/circular hybrid targeting (uses constant heading change prediction).
 *  â¢ Continuous radar lock and adaptive bullet power.
 */
public class MyTank extends AdvancedRobot {

    private double moveDirection = 1;
    private final Random rng = new Random();

    // Per-enemy state
    private final Map<String, Double> enemyEnergy = new HashMap<>();
    private final Map<String, Double> enemyHeading = new HashMap<>();

    @Override
    public void run() {
        setColors(Color.GREEN, Color.BLACK, Color.GRAY);
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        // Spin radar indefinitely; onScannedRobot will retarget/overshoot for lock.
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
        setMaxVelocity(8);

        while (true) {
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        final String name = e.getName();

        /* ---- Movement / Dodging ---- */
        double prevEnergy = enemyEnergy.getOrDefault(name, 100.0);
        double energyDrop = prevEnergy - e.getEnergy();
        if (energyDrop > 0 && energyDrop <= 3.0) {          // enemy likely fired
            moveDirection = -moveDirection;
            setAhead((50 + rng.nextDouble() * 150) * moveDirection);
        }
        enemyEnergy.put(name, e.getEnergy());

        /* ---- Perpendicular movement (always strafe) ---- */
        if (rng.nextDouble() < 0.02) {                      // random reversal
            moveDirection = -moveDirection;
        }

        double perpTurn =
                Utils.normalRelativeAngle(e.getBearingRadians() + Math.PI / 2 - (0.5 * moveDirection));

        // Wall-smoothing / reversal if destination would be outside safe bounds
        double destHeading = getHeadingRadians() + perpTurn;
        double destX = getX() + Math.sin(destHeading) * 120 * moveDirection;
        double destY = getY() + Math.cos(destHeading) * 120 * moveDirection;
        if (destX < 60 || destY < 60
                || destX > getBattleFieldWidth() - 60
                || destY > getBattleFieldHeight() - 60) {
            moveDirection = -moveDirection;
            perpTurn = Utils.normalRelativeAngle(e.getBearingRadians() + Math.PI / 2 - (0.5 * moveDirection));
        }

        setTurnRightRadians(perpTurn);
        setAhead(120 * moveDirection);

        /* ---- Targeting ---- */
        double bulletPower =
                (e.getDistance() < 150 ? 3.0 : (e.getDistance() < 400 ? 2.0 : 1.0));
        bulletPower = Math.min(bulletPower, Math.max(0.1, getEnergy() / 4.0));
        double bulletSpeed = 20 - 3 * bulletPower;

        double myX = getX();
        double myY = getY();

        double absBearing = getHeadingRadians() + e.getBearingRadians();

        double enemyX = myX + Math.sin(absBearing) * e.getDistance();
        double enemyY = myY + Math.cos(absBearing) * e.getDistance();

        double lastHeading = enemyHeading.getOrDefault(name, e.getHeadingRadians());
        double headingChange = e.getHeadingRadians() - lastHeading;
        enemyHeading.put(name, e.getHeadingRadians());

        double enemyVelocity = e.getVelocity();

        // Predict enemy position using constant heading & velocity with heading change
        double deltaTime = 0;
        double predictedX = enemyX;
        double predictedY = enemyY;

        while (deltaTime * bulletSpeed
                < Point2D.distance(myX, myY, predictedX, predictedY)) {
            deltaTime++;
            double predictedHeading = e.getHeadingRadians() + headingChange * deltaTime;
            predictedX += Math.sin(predictedHeading) * enemyVelocity;
            predictedY += Math.cos(predictedHeading) * enemyVelocity;

            if (predictedX < 18.0 || predictedY < 18.0
                    || predictedX > getBattleFieldWidth() - 18.0
                    || predictedY > getBattleFieldHeight() - 18.0) {
                predictedX = Math.min(Math.max(18.0, predictedX), getBattleFieldWidth() - 18.0);
                predictedY = Math.min(Math.max(18.0, predictedY), getBattleFieldHeight() - 18.0);
                break;
            }
        }

        double aim =
                Utils.normalRelativeAngle(Math.atan2(predictedX - myX, predictedY - myY)
                        - getGunHeadingRadians());
        setTurnGunRightRadians(aim);

        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < 0.2) {
            setFire(bulletPower);
        }

        /* ---- Radar lock ---- */
        double radarTurn =
                Utils.normalRelativeAngle(absBearing - getRadarHeadingRadians());
        setTurnRadarRightRadians(radarTurn * 2);            // overshoot for lock
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        moveDirection = -moveDirection;
        setAhead(150 * moveDirection);
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        moveDirection = -moveDirection;
        setAhead((50 + rng.nextDouble() * 150) * moveDirection);
    }
}