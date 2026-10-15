package custom;

import robocode.*;
import robocode.util.Utils;
import robocode.Rules;
import java.awt.*;

/**
 * MyTank â adaptive gun + improved wall-smoothing perpendicular movement
 */
public class MyTank extends AdvancedRobot {

    private int moveDirection = 1;
    private double lastEnemyEnergy = 100.0;
    private double previousEnemyHeading = 0.0;
    private boolean initialScan = true;
    private int bulletsFired = 0;
    private int bulletsHit = 0;

    /* ---- wall-smoothing helpers ---- */
    private static final double WALL_STICK = 140;          // distance to keep from walls
    private static final double WALL_MARGIN = 18;          // bot radius

    private boolean isInsideField(double x, double y) {
        return x > WALL_MARGIN && x < getBattleFieldWidth() - WALL_MARGIN
            && y > WALL_MARGIN && y < getBattleFieldHeight() - WALL_MARGIN;
    }
    private double wallSmoothing(double angle, int orientation) {
        // Adjust angle in small increments until projected point is inside field
        while (!isInsideField(
                getX() + Math.sin(angle) * WALL_STICK,
                getY() + Math.cos(angle) * WALL_STICK)) {
            angle += orientation * 0.05; // 0.05 rad â 2.8Â°
        }
        return angle;
    }

    @Override
    public void run() {
        // Appearance
        setBodyColor(Color.gray);
        setGunColor(Color.darkGray);
        setRadarColor(Color.black);
        setBulletColor(Color.red);

        // Independent gun & radar
        setAdjustRadarForGunTurn(true);
        setAdjustGunForRobotTurn(true);

        // Spin radar indefinitely
        setTurnRadarRight(Double.POSITIVE_INFINITY);

        while (true) {
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        double absBearing = getHeadingRadians() + e.getBearingRadians();
        double distance = e.getDistance();
        double enemyVel = e.getVelocity();
        double enemyHeading = e.getHeadingRadians();
        double headingChange;
        if (initialScan) {
            headingChange = 0;
            initialScan = false;
        } else {
            headingChange = Utils.normalRelativeAngle(enemyHeading - previousEnemyHeading);
        }
        // Clamp headingChange to physical limits
        double maxEnemyTurn = Rules.getTurnRateRadians(enemyVel);
        headingChange = Math.max(-maxEnemyTurn, Math.min(maxEnemyTurn, headingChange));

        double enemyEnergy = e.getEnergy();

        /* ----- adaptive firepower ----- */
        double firePower = Math.min(3.0, Math.max(1.0, 400 / distance));
        double hitRate = bulletsFired > 0 ? (double) bulletsHit / bulletsFired : 1.0;
        if (hitRate < 0.20) {
            firePower = Math.max(1.0, firePower - 0.5);
        } else if (hitRate > 0.40) {
            firePower = Math.min(3.0, firePower + 0.5);
        }
        double bulletSpeed = 20 - 3 * firePower;

        /* ----- circular targeting ----- */
        double predictedX = getX() + distance * Math.sin(absBearing);
        double predictedY = getY() + distance * Math.cos(absBearing);
        double time = 0;
        while (++time * bulletSpeed < distance && time < 40) {
            predictedX += Math.sin(enemyHeading) * enemyVel;
            predictedY += Math.cos(enemyHeading) * enemyVel;
            enemyHeading += headingChange;

            // Simple wall reflection to keep prediction reasonable
            if (predictedX < WALL_MARGIN || predictedX > getBattleFieldWidth() - WALL_MARGIN) enemyVel = -enemyVel;
            if (predictedY < WALL_MARGIN || predictedY > getBattleFieldHeight() - WALL_MARGIN) enemyVel = -enemyVel;

            distance = Math.hypot(predictedX - getX(), predictedY - getY());
        }

        double aimAngle = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        double gunTurn = Utils.normalRelativeAngle(aimAngle - getGunHeadingRadians());
        setTurnGunRightRadians(gunTurn);

        if (getGunHeat() == 0 && Math.abs(gunTurn) < Math.toRadians(5)) {
            setFire(firePower);
            bulletsFired++;
        }

        /* ----- improved perpendicular movement with wall-smoothing ----- */
        double goalAngle = absBearing + moveDirection * Math.PI / 2;
        goalAngle = wallSmoothing(goalAngle, moveDirection);
        setTurnRightRadians(Utils.normalRelativeAngle(goalAngle - getHeadingRadians()));
        setAhead(100 * moveDirection);

        // Occasionally change direction for unpredictability
        if (Math.random() < 0.04) {
            moveDirection *= -1;
        }

        /* ----- radar lock ----- */
        double radarTurn = Utils.normalRelativeAngle(absBearing - getRadarHeadingRadians());
        setTurnRadarRightRadians(radarTurn * 2);

        /* ----- dodge when enemy fires ----- */
        double energyDrop = lastEnemyEnergy - enemyEnergy;
        if (energyDrop > 0 && energyDrop <= 3.0) {
            moveDirection *= -1;
            setAhead((distance / 2 + 50) * moveDirection);
        }
        lastEnemyEnergy = enemyEnergy;
        previousEnemyHeading = e.getHeadingRadians();
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        moveDirection *= -1;
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        moveDirection *= -1;
    }

    @Override
    public void onBulletHit(BulletHitEvent e) {
        bulletsHit++;
    }
}