package custom;

import robocode.AdvancedRobot;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;
import robocode.ScannedRobotEvent;
import robocode.util.Utils;

import java.awt.geom.Point2D;

/**
 * MyTank â round-10.
 *
 * Key updates this round
 * 1. NEW linear lead targeting with quadratic intercept solution.
 *    â If a real solution exists, we fire using linear lead (more accurate
 *      against most movement).  Falls back to previous circular predictor
 *      when no good solution so we never aim head-on.
 * 2. Gun-alignment fix: now uses getGunTurnRemainingRadians() instead of
 *    degree-based API (unit mismatch removed).
 * 3. Slightly looser fire condition (â¤7Â°) to shoot more often.
 *
 * Movement / radar behaviour kept from earlier rounds.
 */
public class MyTank extends AdvancedRobot {

    private static final double MAX_FIRE_POWER = 3.0;
    private static final double WALL_MARGIN   = 60;
    private static final long   DIRECTION_COOLDOWN_TICKS = 20;
    private static final double FIRE_GUN_TURN_THRESHOLD  = Math.toRadians(7);

    private double previousEnemyEnergy = 100;
    private long   lastScanTick = 0;
    private int    moveDirection = 1;
    private long   lastDirectionChangeTick = 0;

    // For circular fallback targeting
    private double prevEnemyHeading = 0;
    private boolean hasPrevHeading = false;

    @Override
    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        lastScanTick = getTime();

        // Radar initial sweep
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);

        while (true) {
            if (getTime() - lastScanTick > 5) {
                setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
            }
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {

        double absBearing = getHeadingRadians() + e.getBearingRadians();

        /* ------------ Movement ------------- */
        // Detect enemy fire (energy drop) and possibly dodge
        double energyDrop = previousEnemyEnergy - e.getEnergy();
        long now = getTime();
        lastScanTick = now;
        if (energyDrop > 0 && energyDrop <= 3 && (now - lastDirectionChangeTick) > DIRECTION_COOLDOWN_TICKS) {
            moveDirection *= -1;
            lastDirectionChangeTick = now;
        }
        previousEnemyEnergy = e.getEnergy();

        // Move perpendicular to enemy with slight randomness
        double randomOffset = (Math.random() - 0.5) * 0.5; // Â±0.25 rad
        double desiredAngle = absBearing + Math.PI / 2 * moveDirection + randomOffset;

        // Wall-smoothing
        double moveDist = Math.min(300, Math.max(120, e.getDistance() * 0.6)) + (Math.random() - 0.5) * 40;
        double bfW = getBattleFieldWidth();
        double bfH = getBattleFieldHeight();
        double destX = getX() + Math.sin(desiredAngle) * moveDist;
        double destY = getY() + Math.cos(desiredAngle) * moveDist;
        int smoothIter = 0;
        while ((destX < WALL_MARGIN || destX > bfW - WALL_MARGIN ||
                destY < WALL_MARGIN || destY > bfH - WALL_MARGIN) && smoothIter++ < 8) {
            desiredAngle += moveDirection * 0.20;
            destX = getX() + Math.sin(desiredAngle) * moveDist;
            destY = getY() + Math.cos(desiredAngle) * moveDist;
        }

        setTurnRightRadians(Utils.normalRelativeAngle(desiredAngle - getHeadingRadians()));
        setAhead(moveDist);

        /* ------------ Targeting ------------- */
        // Dynamic bullet power
        double bulletPower;
        if (getEnergy() < 15) {
            bulletPower = 1.0;
        } else {
            bulletPower = Math.min(MAX_FIRE_POWER, 1200 / e.getDistance());
        }
        bulletPower = Math.min(bulletPower, e.getEnergy() / 3);
        bulletPower = Math.max(0.3, bulletPower);
        double bulletSpeed = 20 - 3 * bulletPower;

        // Current enemy position
        double enemyX = getX() + e.getDistance() * Math.sin(absBearing);
        double enemyY = getY() + e.getDistance() * Math.cos(absBearing);

        // Enemy velocity components
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();
        double enemyVelX = enemyVelocity * Math.sin(enemyHeading);
        double enemyVelY = enemyVelocity * Math.cos(enemyHeading);

        // Solve quadratic for linear targeting
        double deltaX = enemyX - getX();
        double deltaY = enemyY - getY();

        double A = enemyVelX * enemyVelX + enemyVelY * enemyVelY - bulletSpeed * bulletSpeed;
        double B = 2 * (enemyVelX * deltaX + enemyVelY * deltaY);
        double C = deltaX * deltaX + deltaY * deltaY;

        double predictedX, predictedY;

        double discriminant = B * B - 4 * A * C;
        boolean usedLinear = false;
        if (Math.abs(A) < 1e-6 || discriminant < 0) {
            // Fallback to circular prediction (old method)
            double headingDelta = hasPrevHeading ? Utils.normalRelativeAngle(enemyHeading - prevEnemyHeading) : 0;
            prevEnemyHeading = enemyHeading;
            hasPrevHeading = true;

            predictedX = enemyX;
            predictedY = enemyY;
            double predictedHeading = enemyHeading;
            int deltaTime = 0;

            while ((++deltaTime) * bulletSpeed <
                    Point2D.distance(getX(), getY(), predictedX, predictedY)) {
                predictedX += enemyVelocity * Math.sin(predictedHeading);
                predictedY += enemyVelocity * Math.cos(predictedHeading);
                predictedHeading += headingDelta;
                predictedX = Math.max(WALL_MARGIN, Math.min(bfW - WALL_MARGIN, predictedX));
                predictedY = Math.max(WALL_MARGIN, Math.min(bfH - WALL_MARGIN, predictedY));
            }
        } else {
            double t1 = (-B + Math.sqrt(discriminant)) / (2 * A);
            double t2 = (-B - Math.sqrt(discriminant)) / (2 * A);
            double time = Math.min(t1, t2);
            if (time < 0) time = Math.max(t1, t2);
            if (time < 0) time = 0;

            predictedX = enemyX + enemyVelX * time;
            predictedY = enemyY + enemyVelY * time;

            predictedX = Math.max(WALL_MARGIN, Math.min(bfW - WALL_MARGIN, predictedX));
            predictedY = Math.max(WALL_MARGIN, Math.min(bfH - WALL_MARGIN, predictedY));
            usedLinear = true;
        }

        double aimAngle = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(),
                predictedY - getY()));

        setTurnGunRightRadians(Utils.normalRelativeAngle(aimAngle - getGunHeadingRadians()));

        if (getGunHeat() == 0
                && Math.abs(getGunTurnRemainingRadians()) < FIRE_GUN_TURN_THRESHOLD
                && bulletPower >= 0.1) {
            setFire(bulletPower);
        }

        /* ------------ Radar lock ------------ */
        double radarTurn = Utils.normalRelativeAngle(absBearing - getRadarHeadingRadians());
        setTurnRadarRightRadians(radarTurn + (radarTurn < 0 ? -0.03 : 0.03));

        // Debug: optionally print when linear was used
        // if (usedLinear) out.println("Linear shot!");
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        setTurnRight(90);
        setAhead(120);
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        moveDirection *= -1;
        setAhead(120);
    }
}