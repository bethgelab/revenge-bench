package custom;

import robocode.*;
import robocode.util.Utils;

import java.awt.*;

/**
 * MyTank â improved bot (Round 2):
 * â Keeps radar locked on opponent
 * â Perpendicular movement with random direction changes and basic wall/bullet evasion
 * â Circular targeting (accounts for enemy heading change) with variable firepower
 */
public class MyTank extends AdvancedRobot {
    private static final double MAX_FIRE_POWER = 3.0;
    private static final double MIN_FIRE_POWER = 0.8;
    private static final double CHANGE_DIR_PROB = 0.02;

    private int moveDirection = 1;

    // For circular targeting
    private double prevEnemyHeading = 0;
    private boolean firstScan = true;

    @Override
    public void run() {
        // Aesthetics
        setBodyColor(Color.DARK_GRAY);
        setGunColor(Color.GRAY);
        setRadarColor(Color.YELLOW);
        setBulletColor(Color.CYAN);
        setScanColor(Color.ORANGE);

        // Decouple gun & radar
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        // Initial radar spin
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);

        while (true) {
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        double enemyDistance = e.getDistance();
        double enemyBearing = e.getBearingRadians();
        double absoluteBearing = getHeadingRadians() + enemyBearing;

        // ---------------- Movement ----------------
        double turn = enemyBearing + Math.PI / 2;
        if (Math.random() < CHANGE_DIR_PROB) {
            moveDirection *= -1;                 // random direction change
        }
        setTurnRightRadians(Utils.normalRelativeAngle(turn));
        setAhead(moveDirection * (enemyDistance / 2 + 50));

        // ---------------- Targeting ----------------
        double firePower = Math.min(MAX_FIRE_POWER, Math.max(MIN_FIRE_POWER, 400 / enemyDistance));
        double bulletSpeed = 20 - 3 * firePower;

        // Enemy info
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();

        // Heading change per tick (for circular targeting)
        double headingChange = 0;
        if (!firstScan) {
            headingChange = Utils.normalRelativeAngle(enemyHeading - prevEnemyHeading);
        } else {
            firstScan = false;
        }
        prevEnemyHeading = enemyHeading;

        // Current enemy coordinates
        double enemyX = getX() + enemyDistance * Math.sin(absoluteBearing);
        double enemyY = getY() + enemyDistance * Math.cos(absoluteBearing);

        // Predict future position
        double predictedX = enemyX;
        double predictedY = enemyY;
        double predictedHeading = enemyHeading;

        double bulletTravel = 0;
        int timeStep = 0;
        // Iterate until bullet could reach the predicted position
        while (timeStep < 40) { // cap iterations to avoid heavy cpu
            predictedX += enemyVelocity * Math.sin(predictedHeading);
            predictedY += enemyVelocity * Math.cos(predictedHeading);
            predictedHeading += headingChange;

            // Keep predicted point within battlefield (account for bot radius 18)
            predictedX = Math.max(18, Math.min(predictedX, getBattleFieldWidth() - 18));
            predictedY = Math.max(18, Math.min(predictedY, getBattleFieldHeight() - 18));

            timeStep++;
            bulletTravel = timeStep * bulletSpeed;
            double dist = Math.hypot(predictedX - getX(), predictedY - getY());
            if (bulletTravel >= dist) {
                break;
            }
        }

        double aim = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        setTurnGunRightRadians(Utils.normalRelativeAngle(aim - getGunHeadingRadians()));

        if (getGunHeat() == 0 && getEnergy() > firePower) {
            setFire(firePower);
        }

        // ---------------- Radar lock ----------------
        double radarTurn = Utils.normalRelativeAngle(absoluteBearing - getRadarHeadingRadians());
        double extraTurn = Math.min(Math.atan(36.0 / enemyDistance), Rules.RADAR_TURN_RATE_RADIANS);
        setTurnRadarRightRadians(radarTurn + (radarTurn < 0 ? -extraTurn : extraTurn));
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        moveDirection *= -1;
        setAhead(150 * moveDirection);
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        // Simple evasive action: reverse
        moveDirection *= -1;
    }
}